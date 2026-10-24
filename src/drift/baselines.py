"""Threshold baselines B1-B4 (PLAN.md Section 4, Phase 4).

B1: MAP < 65 sustained >= 60s (the standard alarm). This is literally the
primary event detector (labels.detect_primary_events) -- by construction
its alert fires exactly at the event's own start time, i.e. zero lead time.
Not part of the generic risk/threshold framework below; use b1_alert_times.

B2-B4 are each a continuous "risk" column added to a case's window rows,
then tuned and turned into discrete alerts by alarms.py's SAME
threshold-search and refractory/suppression logic the model uses --
"all tuned to match the operating-point false-alarm rate, same as the
model." PLAN.md gives B2 an example tuning range (70-75 mmHg) and names
B3's default (shock index > 0.9); we don't force the search into those
example ranges (that would be circular -- tuning to literally match the
target false-alarm rate is more honest and is what's reported), but the
resulting effective threshold is reported either way.

- B2 risk = -map (lower MAP -> higher risk); thresholding -map is
  equivalent to a plain "MAP below some cutoff" rule.
- B3 risk = shock_index (HR/SBP), matching PLAN.md directly.
- B4 risk = -map_slope_5 (the most recent/responsive slope window): a
  faster MAP decline gives a higher risk. Using the 5-min window rather
  than 10/15 is a documented choice (PLAN.md doesn't pin which window),
  made for the same reason a "slope rule" is useful at all -- reacting to
  recent trend, not an average over a slower window.
"""

from __future__ import annotations

import pandas as pd


def add_baseline_risk_columns(windows_df: pd.DataFrame) -> pd.DataFrame:
    out = windows_df.copy()
    out["b2_risk"] = -out["map"]
    out["b3_risk"] = out["shock_index"]
    out["b4_risk"] = -out["map_slope_5"]
    return out


def b1_alert_times(event_starts_s: list[float]) -> list[float]:
    """The standard alarm's alerts: exactly the primary events' own start
    times (zero lead time, by definition of what the standard alarm is)."""
    return sorted(event_starts_s)
