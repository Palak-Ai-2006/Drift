"""Cohort tests: toy series for the vitals-based eligibility functions (no
real bulk data needed, per the Oct 24 "option 3" decision -- write and test
Phase 2 code against synthetic data only, hold real execution for the
event), plus integration checks against the real cached clinical table
(data/manual/cases.csv, already-approved, no new downloads) for the
clinical-table-derivable functions and the Cohort B rule."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import cohort, config, vitaldb_io  # noqa: E402


# ---------------------------------------------------------------------------
# Toy-data tests: usable_monitored_minutes / is_usable_monitoring_sufficient
# ---------------------------------------------------------------------------
def _toy_vitals(times_s, hr=None, sbp=None, dbp=None, map_=None):
    n = len(times_s)
    return pd.DataFrame({
        "Time": times_s,
        config.TRACK_HR: hr if hr is not None else [70.0] * n,
        config.TRACK_SBP: sbp if sbp is not None else [120.0] * n,
        config.TRACK_DBP: dbp if dbp is not None else [70.0] * n,
        config.TRACK_MAP: map_ if map_ is not None else [90.0] * n,
    })


def test_usable_monitored_minutes_excludes_pre_exclusion_window():
    # Anesthesia starts at t=0; exclusion window is 15 min (900s). Samples
    # before t=900 should not count even though they're "usable" (all 4
    # tracks present).
    times = [0, 600, 900, 1200, 1500]  # seconds
    df = _toy_vitals(times)
    minutes = cohort.usable_monitored_minutes(df, anesthesia_start_s=0)
    # usable samples within window: t=900,1200,1500 -> contiguous span 600s = 10 min
    assert minutes == pytest.approx(10.0)


def test_usable_monitored_minutes_excludes_rows_missing_any_track():
    times = [1000, 1030, 1060, 1090]
    hr = [70, 70, np.nan, 70]  # one row missing HR -> breaks contiguity
    df = _toy_vitals(times, hr=hr)
    minutes = cohort.usable_monitored_minutes(df, anesthesia_start_s=0)
    # Interval t=1000-1030 has both endpoints usable (30s counted). Both
    # intervals touching t=1060 (unusable) are excluded. -> 30s = 0.5 min
    assert minutes == pytest.approx(0.5)


def test_usable_monitored_minutes_respects_op_window():
    times = [1000, 1030, 1060, 5000, 5030]
    df = _toy_vitals(times)
    minutes = cohort.usable_monitored_minutes(
        df, anesthesia_start_s=0, op_start_s=900, op_end_s=1100,
    )
    # only t=1000,1030,1060 are within [900,1100] -> 60s = 1 min
    assert minutes == pytest.approx(1.0)


def test_usable_monitored_minutes_zero_when_no_usable_rows():
    times = [0, 100]
    df = _toy_vitals(times)
    minutes = cohort.usable_monitored_minutes(df, anesthesia_start_s=10_000)
    assert minutes == 0.0


def test_is_usable_monitoring_sufficient_threshold():
    # Build exactly config.ELIGIBLE_MIN_MONITORED_MIN_AFTER_EXCLUSION minutes
    # of contiguous usable monitoring, starting right after the exclusion window.
    exclusion_end_s = config.EXCLUSION_WINDOW_AFTER_ANESTHESIA_START_MIN * 60
    span_s = config.ELIGIBLE_MIN_MONITORED_MIN_AFTER_EXCLUSION * 60
    times = [exclusion_end_s, exclusion_end_s + span_s]
    df = _toy_vitals(times)
    assert cohort.is_usable_monitoring_sufficient(df, anesthesia_start_s=0) is True

    times_short = [exclusion_end_s, exclusion_end_s + span_s - 60]
    df_short = _toy_vitals(times_short)
    assert cohort.is_usable_monitoring_sufficient(df_short, anesthesia_start_s=0) is False


# ---------------------------------------------------------------------------
# Toy-data tests: assign_cohort_b (primary rule + fallback)
# ---------------------------------------------------------------------------
def _toy_cases(n, ebl, rbc):
    return pd.DataFrame({
        config.COL_CASEID: range(n),
        config.COL_INTRAOP_EBL: ebl,
        config.COL_INTRAOP_RBC: rbc,
    })


def test_assign_cohort_b_uses_primary_rule_when_counts_are_sufficient():
    # 200 eligible cases, 80 with EBL>=500 (40%, well above both fallback bars).
    n = 200
    ebl = [600.0] * 80 + [100.0] * 120
    rbc = [0.0] * n
    cases_df = _toy_cases(n, ebl, rbc)
    eligible = pd.Series([True] * n)
    result = cohort.assign_cohort_b(cases_df, eligible)
    assert result.rule_used == "primary"
    assert result.n_cohort_b == 80
    assert result.n_eligible == 200


def test_assign_cohort_b_falls_back_when_too_few_cases():
    # 200 eligible cases, unique EBL values all under 500 (so none trigger
    # the primary EBL rule), only 10 transfused (< 60-case floor) ->
    # primary rule yields 10 cases, triggers the fallback.
    n = 200
    ebl = [i * 2.45 for i in range(n)]  # unique values, 0..~487.55, all <500
    rbc = [0.0] * 190 + [1.0] * 10
    cases_df = _toy_cases(n, ebl, rbc)
    eligible = pd.Series([True] * n)
    result = cohort.assign_cohort_b(cases_df, eligible)
    assert result.rule_used == "fallback_top_quartile"
    # top quartile of 200 unique EBL values = 50 cases
    assert result.n_cohort_b == pytest.approx(50, abs=2)


def test_assign_cohort_b_falls_back_when_below_fraction_even_if_above_count():
    # 1000 eligible cases, 65 meet the primary rule -> above the 60-case
    # floor but only 6.5% of eligible, below the 10% fraction floor.
    n = 1000
    ebl = [600.0] * 65 + [50.0] * 935
    rbc = [0.0] * n
    cases_df = _toy_cases(n, ebl, rbc)
    eligible = pd.Series([True] * n)
    result = cohort.assign_cohort_b(cases_df, eligible)
    assert result.rule_used == "fallback_top_quartile"


def test_assign_cohort_b_only_considers_eligible_cases():
    n = 10
    ebl = [600.0] * 10  # all would qualify by EBL
    rbc = [0.0] * n
    cases_df = _toy_cases(n, ebl, rbc)
    eligible = pd.Series([True] * 5 + [False] * 5)
    result = cohort.assign_cohort_b(cases_df, eligible)
    assert result.n_eligible == 5
    # only the first 5 (eligible) rows can be in cohort B
    assert result.membership.iloc[5:].sum() == 0


def test_assign_cohort_b_transfusion_alone_qualifies():
    n = 10
    ebl = [0.0] * n
    rbc = [0.0] * 9 + [2.0]  # last case transfused, no high EBL
    cases_df = _toy_cases(n, ebl, rbc)
    eligible = pd.Series([True] * n)
    result = cohort.assign_cohort_b(cases_df, eligible)
    assert result.membership.iloc[9] == True  # noqa: E712


# ---------------------------------------------------------------------------
# Integration checks against the real cached clinical table (already
# approved; no new downloads -- same cases.csv Phase 1 already used).
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real_cases_df():
    return vitaldb_io.load_case_table()


def test_clinical_table_eligibility_matches_known_real_counts(real_cases_df):
    elig = cohort.clinical_table_eligibility(real_cases_df)
    # These exact counts were confirmed during Phase 1 (DATA_CARD.md,
    # HANDOFF.md): age>=18 -> 6331 of 6388; arterial line -> 3463 of 6388.
    assert int(elig["age_ok"].sum()) == 6331
    assert int(elig["arterial_ok"].sum()) == 3463
    assert len(elig) == 6388


def test_clinical_eligibility_funnel_runs_on_real_data(real_cases_df):
    elig = cohort.clinical_table_eligibility(real_cases_df)
    funnel = cohort.clinical_eligibility_funnel(elig)
    assert funnel["total_cases"] == 6388
    assert funnel["age_and_arterial_ok"] <= funnel["age_ok"]
    assert funnel["age_and_arterial_ok"] <= funnel["arterial_ok"]


def test_build_cohort_table_is_marked_not_final(real_cases_df):
    elig = cohort.clinical_table_eligibility(real_cases_df)
    table = cohort.build_cohort_table(real_cases_df, elig)
    assert table.attrs["is_final"] is False
    assert "cohort_a" in table.columns
    assert "cohort_b" in table.columns
    # Cohort B must be a subset of Cohort A (eligibility implied).
    assert (table["cohort_b"] & ~table["cohort_a"]).sum() == 0


# ---------------------------------------------------------------------------
# Bulk-download sample selection
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real_cohort_table(real_cases_df):
    elig = cohort.clinical_table_eligibility(real_cases_df)
    return cohort.build_cohort_table(real_cases_df, elig)


def test_select_bulk_download_sample_respects_target_and_fraction(real_cohort_table):
    selection = cohort.select_bulk_download_sample(real_cohort_table, target_n=300, high_loss_fraction=1 / 3)
    assert len(selection) == 300
    n_high_loss = int((selection["selection_group"] == "high_loss_or_transfused").sum())
    n_random = int((selection["selection_group"] == "random_arterial_line").sum())
    assert n_high_loss == 100  # round(300 * 1/3)
    assert n_random == 200
    assert n_high_loss + n_random == len(selection)


def test_select_bulk_download_sample_is_deterministic(real_cohort_table):
    a = cohort.select_bulk_download_sample(real_cohort_table, target_n=50)
    b = cohort.select_bulk_download_sample(real_cohort_table, target_n=50)
    pd.testing.assert_frame_equal(a, b)


def test_select_bulk_download_sample_only_from_clinical_eligible(real_cohort_table):
    selection = cohort.select_bulk_download_sample(real_cohort_table, target_n=100)
    selected_ids = set(selection[config.COL_CASEID])
    eligible_ids = set(real_cohort_table.loc[real_cohort_table["clinical_eligible"], config.COL_CASEID])
    assert selected_ids.issubset(eligible_ids)
    assert len(selected_ids) == len(selection)  # no duplicates


def test_select_bulk_download_sample_group_membership_matches_cohort_b(real_cohort_table):
    selection = cohort.select_bulk_download_sample(real_cohort_table, target_n=100)
    cohort_b_ids = set(real_cohort_table.loc[real_cohort_table["cohort_b"], config.COL_CASEID])
    high_loss_ids = set(selection.loc[selection["selection_group"] == "high_loss_or_transfused", config.COL_CASEID])
    random_ids = set(selection.loc[selection["selection_group"] == "random_arterial_line", config.COL_CASEID])
    assert high_loss_ids.issubset(cohort_b_ids)
    assert random_ids.isdisjoint(cohort_b_ids)
