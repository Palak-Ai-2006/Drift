"""Eligibility, exclusion windows, and Cohort A / Cohort B assignment.

Phase 2 (PLAN.md Section 2, Section 6 Phase 2).

Eligible case: age >= 18; invasive arterial numerics present; >= 60 min usable
monitoring after the exclusion window (first 15 min after anesthesia start,
plus anything outside the operation window).

This module splits eligibility into two layers because of what data is
actually available right now (see HANDOFF.md section 2):
  - clinical_table_eligibility(): age + arterial-line presence, computable
    from the clinical table alone (data/manual/cases.csv), which we have for
    all 6,388 real cases.
  - usable_monitored_minutes() / is_usable_monitoring_sufficient(): the
    >=60-min-after-exclusion criterion, which needs real per-case vitals.
    These are implemented and unit-tested on synthetic toy series (per
    PLAN.md's own Phase 2 accept criterion: "event-detector unit tests on
    toy series" -- the same toy-data approach applies here), but have not
    been run at scale because that needs the bulk per-case download, which
    is still gated (Decision 1).

Cohort B rule (RBC transfusion OR intraop_ebl >= 500 mL, with the
top-quartile fallback) is fixed in config.py per the Oct 24 decision and
must not change after results are seen.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import config


# ---------------------------------------------------------------------------
# Clinical-table-derivable eligibility (real data available now)
# ---------------------------------------------------------------------------
def clinical_table_eligibility(cases_df: pd.DataFrame) -> pd.DataFrame:
    """age_ok and arterial_ok flags, computable from the clinical table alone.

    Does NOT include the usable-monitoring-minutes criterion -- that needs
    real vitals (see module docstring). The combined 'clinical_eligible'
    column here is a necessary-but-not-sufficient precondition for the full
    PLAN.md eligibility definition, not the final eligible-case set.
    """
    out = pd.DataFrame()
    out[config.COL_CASEID] = cases_df[config.COL_CASEID]
    out["age_ok"] = cases_df[config.COL_AGE] >= config.ELIGIBLE_MIN_AGE_YEARS
    a1 = cases_df[config.COL_ALINE1].notna() & (cases_df[config.COL_ALINE1].astype(str).str.strip() != "")
    a2 = cases_df[config.COL_ALINE2].notna() & (cases_df[config.COL_ALINE2].astype(str).str.strip() != "")
    out["arterial_ok"] = a1 | a2
    out["clinical_eligible"] = out["age_ok"] & out["arterial_ok"]
    return out


def clinical_eligibility_funnel(clinical_elig_df: pd.DataFrame) -> dict:
    """Counts at each clinical-table-derivable funnel step (Phase 1-level
    data only). The real DATA_CARD.md funnel also needs the vitals-based
    step below, added once bulk data exists."""
    total = len(clinical_elig_df)
    age_ok = int(clinical_elig_df["age_ok"].sum())
    arterial_ok = int(clinical_elig_df["arterial_ok"].sum())
    both = int(clinical_elig_df["clinical_eligible"].sum())
    return {
        "total_cases": total,
        "age_ok": age_ok,
        "arterial_ok": arterial_ok,
        "age_and_arterial_ok": both,
        "note": (
            "This funnel stops at the clinical-table-derivable criteria. "
            "The >=60min-usable-monitoring-after-exclusion criterion still "
            "needs real per-case vitals (bulk download, not yet approved)."
        ),
    }


# ---------------------------------------------------------------------------
# Vitals-based eligibility (usable monitoring minutes) -- toy-tested only
# ---------------------------------------------------------------------------
def usable_monitored_minutes(
    vitals_df: pd.DataFrame,
    anesthesia_start_s: float,
    op_start_s: float | None = None,
    op_end_s: float | None = None,
    time_col: str = "Time",
    required_tracks: tuple[str, ...] = config.REQUIRED_NUMERIC_TRACKS,
    exclusion_window_min: float = config.EXCLUSION_WINDOW_AFTER_ANESTHESIA_START_MIN,
) -> float:
    """Minutes of usable monitoring (all required tracks non-NaN,
    post-artifact-rejection) within the operation window, after excluding
    the first `exclusion_window_min` minutes following anesthesia start.

    vitals_df is expected to already be artifact-rejected (preprocess.
    reject_artifacts) and gap-interpolated (preprocess.interpolate_short_gaps)
    by the caller -- this function only measures coverage, it doesn't clean.
    """
    d = vitals_df.sort_values(time_col)
    exclusion_end_s = anesthesia_start_s + exclusion_window_min * 60.0

    mask = d[time_col] >= exclusion_end_s
    if op_start_s is not None:
        mask &= d[time_col] >= op_start_s
    if op_end_s is not None:
        mask &= d[time_col] <= op_end_s

    window = d.loc[mask].sort_values(time_col)
    if len(window) < 2:
        return 0.0

    usable = window[list(required_tracks)].notna().all(axis=1).to_numpy()
    t = window[time_col].to_numpy(dtype=float)
    diffs = t[1:] - t[:-1]
    # An interval between two consecutive raw samples counts as usable time
    # only if BOTH endpoints are usable -- an unusable row in between must
    # not let the interval on either side of it get silently bridged over.
    both_usable = usable[:-1] & usable[1:]
    total_s = diffs[both_usable].sum()
    return float(total_s) / 60.0


def is_usable_monitoring_sufficient(
    vitals_df: pd.DataFrame,
    anesthesia_start_s: float,
    op_start_s: float | None = None,
    op_end_s: float | None = None,
    time_col: str = "Time",
) -> bool:
    minutes = usable_monitored_minutes(
        vitals_df, anesthesia_start_s, op_start_s=op_start_s, op_end_s=op_end_s, time_col=time_col,
    )
    return bool(minutes >= config.ELIGIBLE_MIN_MONITORED_MIN_AFTER_EXCLUSION)


# ---------------------------------------------------------------------------
# Cohort B assignment (Oct 24 decision -- fixed rule + documented fallback)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CohortBResult:
    membership: pd.Series  # bool, indexed like the input
    rule_used: str  # "primary" or "fallback_top_quartile"
    n_eligible: int
    n_cohort_b: int


def assign_cohort_b(cases_df: pd.DataFrame, eligible_mask: pd.Series) -> CohortBResult:
    """Apply the fixed Cohort B rule to the ELIGIBLE subset only.

    Primary: RBC transfusion OR intraop_ebl >= config.COHORT_B_MIN_EBL_ML.
    Fallback (applied only if the primary rule yields fewer than
    config.COHORT_B_FALLBACK_MIN_CASES cases, or under
    config.COHORT_B_FALLBACK_MIN_FRACTION_OF_ELIGIBLE of eligible cases):
    top quartile of intraop_ebl among eligible cases.

    This function does not itself decide "eligible" -- callers pass the
    final eligible_mask once real vitals-based eligibility exists. Until
    then, callers should pass the clinical_eligible proxy and clearly label
    any resulting counts as preliminary (see DATA_CARD.md).
    """
    eligible_mask = eligible_mask.reindex(cases_df.index, fill_value=False)
    n_eligible = int(eligible_mask.sum())

    transfused = cases_df[config.COL_INTRAOP_RBC].notna() & (cases_df[config.COL_INTRAOP_RBC] > 0)
    high_ebl = cases_df[config.COL_INTRAOP_EBL] >= config.COHORT_B_MIN_EBL_ML
    primary = (transfused | high_ebl) & eligible_mask
    n_primary = int(primary.sum())

    min_cases = config.COHORT_B_FALLBACK_MIN_CASES
    min_fraction = config.COHORT_B_FALLBACK_MIN_FRACTION_OF_ELIGIBLE
    needs_fallback = n_eligible > 0 and (
        n_primary < min_cases or (n_primary / n_eligible) < min_fraction
    )

    if not needs_fallback:
        return CohortBResult(membership=primary, rule_used="primary", n_eligible=n_eligible, n_cohort_b=n_primary)

    eligible_ebl = cases_df.loc[eligible_mask, config.COL_INTRAOP_EBL]
    if eligible_ebl.dropna().empty:
        fallback = pd.Series(False, index=cases_df.index)
    else:
        q75 = eligible_ebl.quantile(0.75)
        fallback = (cases_df[config.COL_INTRAOP_EBL] >= q75) & eligible_mask
    n_fallback = int(fallback.sum())
    return CohortBResult(
        membership=fallback, rule_used="fallback_top_quartile", n_eligible=n_eligible, n_cohort_b=n_fallback,
    )


# ---------------------------------------------------------------------------
# Bulk-download case selection (PLAN.md Section 6 Phase 1 step 5 / Phase 2):
# "target 300-500 cases; about a third high blood loss or transfused, the
# rest random arterial-line cases." Deterministic (fixed seed), draws from
# the clinical-table-eligible pool only (age_ok & arterial_ok), with the
# cohort_b_rule_used already fixed at the time this runs.
# ---------------------------------------------------------------------------
def select_bulk_download_sample(
    cohort_df: pd.DataFrame,
    target_n: int = config.DOWNLOAD_TARGET_CASES_MAX,
    high_loss_fraction: float = config.DOWNLOAD_HIGH_LOSS_OR_TRANSFUSED_FRACTION_TARGET,
    seed: int = config.RANDOM_SEED,
) -> pd.DataFrame:
    """Select which caseids to bulk-download.

    cohort_df is the output of build_cohort_table() (or anything with
    caseid/clinical_eligible/cohort_b columns). Returns a DataFrame with
    columns [caseid, selection_group] where selection_group is
    "high_loss_or_transfused" or "random_arterial_line", caseid ascending
    within each group for a stable, inspectable order (the random_state
    draw itself is what makes the sample deterministic, not this sort).
    """
    pool = cohort_df.loc[cohort_df["clinical_eligible"]]
    cohort_b_pool = pool.loc[pool["cohort_b"], config.COL_CASEID]
    other_pool = pool.loc[~pool["cohort_b"], config.COL_CASEID]

    n_cohort_b_target = round(target_n * high_loss_fraction)
    n_cohort_b = min(n_cohort_b_target, len(cohort_b_pool))
    n_other = min(target_n - n_cohort_b, len(other_pool))

    cohort_b_sample = cohort_b_pool.sample(n=n_cohort_b, random_state=seed) if n_cohort_b > 0 else cohort_b_pool.iloc[0:0]
    other_sample = other_pool.sample(n=n_other, random_state=seed) if n_other > 0 else other_pool.iloc[0:0]

    out = pd.concat([
        pd.DataFrame({config.COL_CASEID: cohort_b_sample.sort_values().to_numpy(), "selection_group": "high_loss_or_transfused"}),
        pd.DataFrame({config.COL_CASEID: other_sample.sort_values().to_numpy(), "selection_group": "random_arterial_line"}),
    ], ignore_index=True)
    return out


def build_cohort_table(cases_df: pd.DataFrame, clinical_elig_df: pd.DataFrame) -> pd.DataFrame:
    """Assemble the (currently partial -- see module docstring) cohort table.

    Uses clinical_eligible as a stand-in for the full eligibility definition
    until real vitals-based eligibility exists. Marked explicitly so this
    is never mistaken for the final cohort.parquet.
    """
    out = clinical_elig_df.copy()
    cohort_b = assign_cohort_b(cases_df, out["clinical_eligible"])
    out["cohort_a"] = out["clinical_eligible"]  # Cohort A = all eligible
    out["cohort_b"] = cohort_b.membership.reindex(out.index, fill_value=False)
    out["cohort_b_rule_used"] = cohort_b.rule_used
    out.attrs["is_final"] = False
    out.attrs["pending"] = (
        "usable-monitoring-minutes eligibility (needs bulk per-case vitals, not yet approved)"
    )
    return out
