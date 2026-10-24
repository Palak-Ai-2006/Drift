"""Evaluation metrics: event-level sensitivity, lead time, false-alarm rate,
AUROC/AUPRC, Brier score, bootstrap confidence intervals by case.

Phase 4 (PLAN.md Section 4, Section 7.5-7.6, Section 8).
Test set is evaluated once; never tuned on afterwards (CLAUDE.md Section 12).
Bootstrap resampling is by case (config.BOOTSTRAP_RESAMPLE_BY), not by row.
scripts/04_train_eval.py writes this module's output to artifacts/metrics.json,
the single source of truth for every number that later appears in the web
demo, DATA_CARD.md, MODEL_CARD.md, Devpost text, and the video script.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from . import config


def event_sensitivity_and_lead_times(
    case_events: dict[int, list[float]],
    case_alerts: dict[int, list[float]],
    caseids: list[int],
    horizon_min: float,
) -> dict:
    """PLAN.md 7.5: an alert a detects an event e if a < e <= a + H. Each
    event's lead time uses the earliest qualifying alert (maximum lead
    time). Returns sensitivity (detected/total) and the list of lead times
    (seconds) for detected events only."""
    n_events = 0
    n_detected = 0
    lead_times_s: list[float] = []
    for caseid in caseids:
        events = case_events.get(caseid, [])
        alerts = sorted(case_alerts.get(caseid, []))
        for e in events:
            n_events += 1
            qualifying = [a for a in alerts if a < e <= a + horizon_min * 60.0]
            if qualifying:
                n_detected += 1
                lead_times_s.append(e - min(qualifying))
    sensitivity = n_detected / n_events if n_events > 0 else float("nan")
    return {
        "n_events": n_events, "n_detected": n_detected, "sensitivity": sensitivity,
        "lead_times_s": lead_times_s,
    }


def lead_time_summary(lead_times_s: list[float]) -> dict:
    if not lead_times_s:
        return {"median_s": float("nan"), "iqr_low_s": float("nan"), "iqr_high_s": float("nan"), "n": 0}
    arr = np.array(lead_times_s, dtype=float)
    return {
        "median_s": float(np.median(arr)),
        "iqr_low_s": float(np.percentile(arr, 25)),
        "iqr_high_s": float(np.percentile(arr, 75)),
        "n": len(arr),
    }


def auroc_auprc_brier(y_true: pd.Series, y_prob: pd.Series) -> dict:
    """Secondary metrics (PLAN.md Phase 4) on rows with a known (non-NaN)
    label only -- censored/unknown-horizon rows are excluded, never
    treated as negatives."""
    mask = y_true.notna() & y_prob.notna()
    yt, yp = y_true[mask], y_prob[mask]
    if yt.nunique() < 2:
        return {"auroc": float("nan"), "auprc": float("nan"), "brier": float("nan"), "n": int(mask.sum())}
    return {
        "auroc": float(roc_auc_score(yt, yp)),
        "auprc": float(average_precision_score(yt, yp)),
        "brier": float(brier_score_loss(yt, yp)),
        "n": int(mask.sum()),
    }


def reliability_curve(y_true: pd.Series, y_prob: pd.Series, n_bins: int = 10) -> dict:
    """Calibration reliability data (PLAN.md Phase 4: "Brier + reliability
    plot"): for n_bins equal-width bins of predicted probability, the mean
    predicted probability and the observed positive fraction, plus the bin
    count. Rows with an unknown (NaN) label are excluded."""
    mask = y_true.notna() & y_prob.notna()
    yt, yp = y_true[mask].to_numpy(dtype=float), y_prob[mask].to_numpy(dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_idx = np.clip(np.digitize(yp, edges[1:-1], right=True), 0, n_bins - 1)
    bins = []
    for b in range(n_bins):
        in_bin = bin_idx == b
        n = int(in_bin.sum())
        bins.append({
            "bin_low": float(edges[b]), "bin_high": float(edges[b + 1]), "n": n,
            "mean_predicted": float(yp[in_bin].mean()) if n > 0 else None,
            "observed_fraction": float(yt[in_bin].mean()) if n > 0 else None,
        })
    return {"bins": bins}


def bootstrap_ci_by_case(
    caseids: list[int],
    metric_fn,
    n_resamples: int = config.BOOTSTRAP_N_RESAMPLES,
    ci_level: float = config.BOOTSTRAP_CI_LEVEL,
    seed: int = config.RANDOM_SEED,
) -> dict:
    """Resample caseids with replacement n_resamples times; metric_fn takes
    a list of caseids (with repeats) and returns a float. Point estimate is
    metric_fn(caseids) itself (no resampling); CI is the resample
    distribution's percentiles. NaN resamples are dropped before taking
    percentiles (e.g. a resample draws zero cases with any events)."""
    point = metric_fn(caseids)
    rng = np.random.RandomState(seed)
    alpha = 1.0 - ci_level
    values = []
    for _ in range(n_resamples):
        sample = rng.choice(caseids, size=len(caseids), replace=True).tolist()
        v = metric_fn(sample)
        if not (v is None or (isinstance(v, float) and np.isnan(v))):
            values.append(v)
    if not values:
        return {"point": point, "ci_low": float("nan"), "ci_high": float("nan"), "n_valid_resamples": 0}
    lo = float(np.percentile(values, 100 * alpha / 2))
    hi = float(np.percentile(values, 100 * (1 - alpha / 2)))
    return {"point": point, "ci_low": lo, "ci_high": hi, "n_valid_resamples": len(values)}
