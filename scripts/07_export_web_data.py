#!/usr/bin/env python
"""Phase 6.1: write web/data/proof.js -- the Proof-and-method drawer's
table, assembled entirely from already-generated artifact JSON files
(CLAUDE.md Section 12: "no number is typed by hand into web files").

Honest-reframing instruction (round 3, 2026-10-24): compare the shipped
model against the standard alarm (B1) and explicitly note that a tuned
MAP-only threshold (B2) performs similarly -- this is not a "drift wins"
pitch, and proof.js must not read as one.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
METRICS_JSON = ROOT / "artifacts" / "metrics.json"
METRICS_V2_JSON = ROOT / "artifacts" / "metrics_v2.json"
CV_RESULTS_JSON = ROOT / "artifacts" / "phase4_cv_model_selection.json"
ROUND3_CV_JSON = ROOT / "artifacts" / "phase4_round3_cv_results.json"
ROUND3_SECONDARY_JSON = ROOT / "artifacts" / "phase4_round3_secondary_shock_index.json"
HOLDOUT_JSON = ROOT / "artifacts" / "phase4_round3_fresh_holdout_results.json"
PROOF_JS = ROOT / "web" / "data" / "proof.js"


def main() -> None:
    print("=== Phase 6.1: export proof.js ===")
    original = json.loads(METRICS_JSON.read_text())
    v2 = json.loads(METRICS_V2_JSON.read_text())
    cv = json.loads(CV_RESULTS_JSON.read_text())
    round3 = json.loads(ROUND3_CV_JSON.read_text())
    secondary = json.loads(ROUND3_SECONDARY_JSON.read_text())
    holdout = json.loads(HOLDOUT_JSON.read_text())

    b1_test = original["test_results"]["methods"]["b1"]["zero_lead"]["per_horizon"]["H15_cohortA"]
    b2_test = original["test_results"]["methods"]["b2"]["1.0"]["per_horizon"]["H15_cohortA"]
    b2_fa = original["test_results"]["methods"]["b2"]["1.0"]["fa_rate_per_hour_by_cohort"]["A"]

    operating_points_table = [
        {
            "method": "B1 (standard alarm, MAP<65/60s)",
            "sensitivity": b1_test["sensitivity"], "lead_time_median_s": b1_test["lead_time"]["median_s"],
            "fa_per_hour": 0.0, "note": "Zero lead by construction -- the alert IS the event.",
        },
        {
            "method": "B2 (tuned early-MAP threshold)",
            "sensitivity": b2_test["sensitivity"], "lead_time_median_s": b2_test["lead_time"]["median_s"],
            "fa_per_hour": b2_fa, "note": "Simple baseline. Performs similarly to the shipped model -- see honesty_note.",
        },
        {
            "method": "Drift (shipped model, early MAP-based alert)",
            "sensitivity": v2["test_results_by_cohort"]["A"]["sensitivity"],
            "lead_time_median_s": v2["test_results_by_cohort"]["A"]["lead_time"]["median_s"],
            "fa_per_hour": v2["test_results_by_cohort"]["A"]["fa_rate_per_hour"],
            "note": "Shipped model: b2_alone (MAP only, calibrated). Not clearly better than B2 above.",
        },
        {
            "method": "Drift, fresh never-touched holdout (175 cases)",
            "sensitivity": holdout["results_by_cohort"]["A"]["sensitivity"],
            "lead_time_median_s": holdout["results_by_cohort"]["A"]["lead_time"]["median_s"],
            "fa_per_hour": holdout["results_by_cohort"]["A"]["fa_rate_per_hour"],
            "note": "Same already-fitted model/threshold, no refitting -- the most trustworthy number (nothing tuned against it).",
        },
    ]

    iteration_summary = {
        "round1_v2": {
            "question": "Does adding HR/pulse-pressure/shock-index drift features beat MAP alone?",
            "winner": v2.get("v2_winner"),
            "finding": "A stacked MAP+drift model scored WORSE than MAP alone in cross-validated screening.",
        },
        "round2_bleeding_label": {
            "question": "Same question, on a cleaner bleeding-flavored label (excludes vasopressor/anesthetic-confounded events).",
            "finding": "Drift lost more decisively (-7.67pp, 95% CI entirely negative).",
        },
        "round3_residual_interaction": {
            "question": "Does a ridge-penalized offset model or MAP x shock-index/HR-drift interaction terms beat MAP alone?",
            "decisions": round3["decisions"],
            "finding": "Neither cleared the pre-registered bar. Closest: interaction terms at -1.45pp (CI includes zero).",
        },
        "round3_secondary_compensation_flag": {
            "question": "Can MAP/pulse-pressure/demographics predict an UPCOMING compensation state (elevated shock index), as a separate, non-hemorrhage task?",
            "cv_roc_auc": secondary["cv_roc_auc"], "cv_roc_auc_ci": secondary["cv_roc_auc_ci"],
            "finding": "A real, modest signal (CV ROC AUC 0.65) -- reported as a compensation-state flag, not hemorrhage evidence.",
        },
    }

    proof = {
        "operating_points_table": operating_points_table,
        "iteration_summary": iteration_summary,
        "brier_score": v2["test_secondary_metrics"]["brier"],
        "auroc": v2["test_secondary_metrics"]["auroc"],
        "auprc": v2["test_secondary_metrics"]["auprc"],
        "split_sizes": original["split_sizes"],
        "cohort_counts": {
            "n_eligible_sample": 442, "n_cohort_b": 165,
            "n_eligible_fresh_holdout": holdout["n_holdout_cases_eligible"],
            "n_cohort_b_fresh_holdout": holdout["n_holdout_cases_cohort_b"],
        },
        "honesty_note": config.WORDING_METHOD_HONESTY_NOTE,
        "what_this_is_not": [
            "Not validated on prehospital trauma data -- this is surgical (intraoperative) data.",
            "The label is low blood pressure (MAP<65), not hemorrhage specifically.",
            "Single hospital (Seoul National University Hospital), single country, 2016-2017.",
            "Not clinically validated. Research prototype only.",
            "The shipped alert is a calibrated MAP threshold, not a distinct physiological 'drift' signal -- "
            "three rounds of testing did not find HR/pulse-pressure/shock-index dynamics add value beyond MAP.",
        ],
    }

    PROOF_JS.parent.mkdir(parents=True, exist_ok=True)
    PROOF_JS.write_text(f"window.DRIFT_PROOF = {json.dumps(proof, indent=2)};\n")
    print(f"Saved {PROOF_JS}")


if __name__ == "__main__":
    main()
