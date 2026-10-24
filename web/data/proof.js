window.DRIFT_PROOF = {
  "operating_points_table": [
    {
      "method": "B1 (standard alarm, MAP<65/60s)",
      "sensitivity": 1.0,
      "lead_time_median_s": 0.0,
      "fa_per_hour": 0.0,
      "note": "Zero lead by construction -- the alert IS the event."
    },
    {
      "method": "B2 (tuned early-MAP threshold)",
      "sensitivity": 0.6013745704467354,
      "lead_time_median_s": 262.0,
      "fa_per_hour": 1.1483481575603558,
      "note": "Simple baseline. Performs similarly to the shipped model -- see honesty_note."
    },
    {
      "method": "Drift (shipped model, early MAP-based alert)",
      "sensitivity": 0.5738831615120275,
      "lead_time_median_s": 261.0,
      "fa_per_hour": 0.9720457433290978,
      "note": "Shipped model: b2_alone (MAP only, calibrated). Not clearly better than B2 above."
    },
    {
      "method": "Drift, fresh never-touched holdout (175 cases)",
      "sensitivity": 0.5252808988764045,
      "lead_time_median_s": 310.0,
      "fa_per_hour": 0.7721849975486194,
      "note": "Same already-fitted model/threshold, no refitting -- the most trustworthy number (nothing tuned against it)."
    }
  ],
  "iteration_summary": {
    "round1_v2": {
      "question": "Does adding HR/pulse-pressure/shock-index drift features beat MAP alone?",
      "winner": "b2_alone",
      "finding": "A stacked MAP+drift model scored WORSE than MAP alone in cross-validated screening."
    },
    "round2_bleeding_label": {
      "question": "Same question, on a cleaner bleeding-flavored label (excludes vasopressor/anesthetic-confounded events).",
      "finding": "Drift lost more decisively (-7.67pp, 95% CI entirely negative)."
    },
    "round3_residual_interaction": {
      "question": "Does a ridge-penalized offset model or MAP x shock-index/HR-drift interaction terms beat MAP alone?",
      "decisions": {
        "residual_ridge": {
          "gain_pp": -8.581752484191508,
          "ci": {
            "point": -0.08581752484191507,
            "ci_low": -0.12230281557923636,
            "ci_high": -0.05017103796769032,
            "n_valid_resamples": 1000
          },
          "adopt_eligible": false
        },
        "interaction_features": {
          "gain_pp": -1.445347786811202,
          "ci": {
            "point": -0.014453477868112019,
            "ci_low": -0.035508771772472046,
            "ci_high": 0.0030207809356136432,
            "n_valid_resamples": 1000
          },
          "adopt_eligible": false
        }
      },
      "finding": "Neither cleared the pre-registered bar. Closest: interaction terms at -1.45pp (CI includes zero)."
    },
    "round3_secondary_compensation_flag": {
      "question": "Can MAP/pulse-pressure/demographics predict an UPCOMING compensation state (elevated shock index), as a separate, non-hemorrhage task?",
      "cv_roc_auc": 0.6498151973604589,
      "cv_roc_auc_ci": {
        "point": 0.6498151973604589,
        "ci_low": 0.5947722516557801,
        "ci_high": 0.7014720392621338,
        "n_valid_resamples": 1000
      },
      "finding": "A real, modest signal (CV ROC AUC 0.65) -- reported as a compensation-state flag, not hemorrhage evidence."
    }
  },
  "brier_score": 0.10348015371339656,
  "auroc": 0.7050939182492701,
  "auprc": 0.288122705249674,
  "split_sizes": {
    "train": 263,
    "val": 88,
    "test": 87
  },
  "cohort_counts": {
    "n_eligible_sample": 442,
    "n_cohort_b": 165,
    "n_eligible_fresh_holdout": 156,
    "n_cohort_b_fresh_holdout": 34
  },
  "honesty_note": "This alert is a calibrated, early MAP-based threshold, not a distinct \u2018drift\u2019 signal. We tested whether heart-rate, pulse-pressure and shock-index dynamics add value beyond MAP alone, under a pre-registered protocol with cross-validation and a held-out test set, across three rounds of iteration. They did not. A simple tuned MAP-only threshold (B2) performs similarly on our test data. Full methodology and results: Proof and method, and MODEL_CARD.md in the project repository.",
  "what_this_is_not": [
    "Not validated on prehospital trauma data -- this is surgical (intraoperative) data.",
    "The label is low blood pressure (MAP<65), not hemorrhage specifically.",
    "Single hospital (Seoul National University Hospital), single country, 2016-2017.",
    "Not clinically validated. Research prototype only.",
    "The shipped alert is a calibrated MAP threshold, not a distinct physiological 'drift' signal -- three rounds of testing did not find HR/pulse-pressure/shock-index dynamics add value beyond MAP."
  ]
};
