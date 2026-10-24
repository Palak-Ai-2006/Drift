"""Alarm logic: threshold + refractory period + suppression rules.

Phase 4 (PLAN.md Section 4, Section 7.3-7.4). Not yet implemented.
Alert when calibrated risk >= the operating-point threshold; refractory period
config.ALARM_REFRACTORY_MIN; suppressed if MAP already < 65 or missing
fraction exceeds config.INSUFFICIENT_DATA_MISSING_FRACTION.
"""
