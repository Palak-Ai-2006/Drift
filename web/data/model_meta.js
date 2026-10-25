window.DRIFT_META = {
  "alert_name": "Drift alert",
  "threshold": 0.35390946502057613,
  "horizon_min": 15,
  "refractory_min": 15,
  "insufficient_data_missing_fraction": 0.3,
  "features": [
    {
      "name": "MAP",
      "display_name": "Mean arterial pressure",
      "explanation": "Current MAP, calibrated into a risk score. No other feature is used by the shipped model."
    }
  ],
  "honesty_note": "Both tabs call their alert a \u2018Drift alert\u2019 for consistency. On real surgical data, it is a calibrated, early MAP-based threshold, not a distinct \u2018drift\u2019 signal. We tested whether heart-rate, pulse-pressure and shock-index dynamics add value beyond MAP alone, under a pre-registered protocol with cross-validation and a held-out test set, across three rounds of iteration. They did not. A simple tuned MAP-only threshold (B2) performs similarly on our test data. Full methodology and results: Proof and method, and MODEL_CARD.md in the project repository.",
  "wording": {
    "monitoring_banner": "Monitoring \u00b7 no alert",
    "alert_banner": "DRIFT ALERT \u00b7 Mean arterial pressure trending low. Check the patient.",
    "insufficient_data_banner": "Not enough data to assess",
    "standard_alarm_not_triggered": "Standard alarm: not triggered",
    "standard_alarm_triggered": "STANDARD ALARM \u00b7 MAP below 65",
    "selected_examples_note": "Selected examples, not average performance. Results across all test cases are in Proof and method.",
    "real_data_badge": "REAL DATA, surgical",
    "real_data_full": "Recorded patient, surgical, VitalDB (Korea). Not live.",
    "replay_banner_tmpl": "Recorded patient, sped up {speed}x. Not live.",
    "footer": "Research prototype \u00b7 not for clinical use \u00b7 no alert does not mean safe.",
    "synthetic_badge": "SYNTHETIC patient, not real data",
    "synthetic_banner": "Simulated patient. Not real data.",
    "simulator_disclaimer": "Illustrative of textbook ATLS physiology. Not confirmed in our data."
  }
};
