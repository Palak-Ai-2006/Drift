"""Artifact rejection and short-gap interpolation for raw VitalDB numeric tracks.

Phase 2 (PLAN.md Section 2, Section 6 Phase 2):
- Artifact rejection: MAP 20-250, SBP 30-300, DBP 10-200, HR 20-250; SBP > DBP;
  no interpolation beyond 60s.
Bounds come from config.ARTIFACT_*; nothing here is hand-tuned outside config.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def reject_artifacts(
    df: pd.DataFrame,
    hr_col: str = config.TRACK_HR,
    sbp_col: str = config.TRACK_SBP,
    dbp_col: str = config.TRACK_DBP,
    map_col: str = config.TRACK_MAP,
) -> pd.DataFrame:
    """Null out physiologically implausible values and SBP<=DBP rows.

    Does not touch rows/columns that aren't present. Returns a copy; the
    input is never mutated.
    """
    out = df.copy()

    def _mask_out_of_range(s: pd.Series, lo: float, hi: float) -> pd.Series:
        return s.where((s >= lo) & (s <= hi))

    if hr_col in out.columns:
        out[hr_col] = _mask_out_of_range(out[hr_col], config.ARTIFACT_HR_MIN, config.ARTIFACT_HR_MAX)
    if sbp_col in out.columns:
        out[sbp_col] = _mask_out_of_range(out[sbp_col], config.ARTIFACT_SBP_MIN, config.ARTIFACT_SBP_MAX)
    if dbp_col in out.columns:
        out[dbp_col] = _mask_out_of_range(out[dbp_col], config.ARTIFACT_DBP_MIN, config.ARTIFACT_DBP_MAX)
    if map_col in out.columns:
        out[map_col] = _mask_out_of_range(out[map_col], config.ARTIFACT_MAP_MIN, config.ARTIFACT_MAP_MAX)

    # SBP must be > DBP; null both where violated (including where either is
    # already NaN from the range check above -- NaN comparisons are False, so
    # rows with one side already nulled are left alone here, which is fine:
    # they're already unusable for either feature individually).
    if sbp_col in out.columns and dbp_col in out.columns:
        violates = out[sbp_col] <= out[dbp_col]
        bad = violates.fillna(False)
        out.loc[bad, [sbp_col, dbp_col]] = np.nan

    return out


def interpolate_short_gaps(
    df: pd.DataFrame,
    value_cols: list[str],
    time_col: str = "Time",
    max_gap_s: float = config.MAX_INTERPOLATION_GAP_S,
) -> pd.DataFrame:
    """Linearly interpolate NaN runs shorter than or equal to max_gap_s
    (measured as actual elapsed time between the bracketing valid samples,
    not sample count -- sampling need not be perfectly uniform). Longer
    gaps, and gaps at the start/end of the series with no bracketing value
    on one side, are left as NaN.
    """
    out = df.sort_values(time_col).reset_index(drop=True)
    time = out[time_col].to_numpy(dtype=float)
    n = len(out)

    for col in value_cols:
        if col not in out.columns:
            continue
        vals = out[col].to_numpy(dtype=float, copy=True)
        is_nan = np.isnan(vals)
        i = 0
        while i < n:
            if not is_nan[i]:
                i += 1
                continue
            j = i
            while j < n and is_nan[j]:
                j += 1
            # NaN run is [i, j). Need a valid sample at i-1 and at j to interpolate.
            if i > 0 and j < n:
                t0, v0 = time[i - 1], vals[i - 1]
                t1, v1 = time[j], vals[j]
                gap_duration = t1 - t0
                if gap_duration <= max_gap_s and t1 != t0:
                    for k in range(i, j):
                        frac = (time[k] - t0) / (t1 - t0)
                        vals[k] = v0 + frac * (v1 - v0)
            i = j
        out[col] = vals

    return out
