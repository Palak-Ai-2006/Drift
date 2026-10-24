"""Toy tests for the patient-level split (PLAN.md Section 4: "by caseid
and subject ID if present, 60/20/20, fixed seed")."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, models  # noqa: E402


def _toy_cases_df(n_cases=100, shared_subject_pairs=()):
    """n_cases cases, one subject each, except shared_subject_pairs ==
    [(caseid_a, caseid_b), ...] which share a subjectid with each other."""
    caseids = list(range(1, n_cases + 1))
    subjectids = list(range(1000, 1000 + n_cases))
    for a, b in shared_subject_pairs:
        subjectids[caseids.index(b)] = subjectids[caseids.index(a)]
    return pd.DataFrame({config.COL_CASEID: caseids, config.COL_SUBJECTID: subjectids})


def test_split_cases_covers_every_caseid_exactly_once():
    cases_df = _toy_cases_df(100)
    caseids = list(cases_df[config.COL_CASEID])
    assignment = models.split_cases(cases_df, caseids)
    assert set(assignment.keys()) == set(caseids)
    assert set(assignment.values()) <= {"train", "val", "test"}


def test_split_cases_approximately_60_20_20():
    cases_df = _toy_cases_df(500)
    caseids = list(cases_df[config.COL_CASEID])
    assignment = models.split_cases(cases_df, caseids)
    counts = pd.Series(assignment.values()).value_counts()
    assert counts["train"] / 500 == pytest.approx(0.6, abs=0.02)
    assert counts["val"] / 500 == pytest.approx(0.2, abs=0.02)
    assert counts["test"] / 500 == pytest.approx(0.2, abs=0.02)


def test_split_cases_keeps_shared_subject_cases_together():
    cases_df = _toy_cases_df(100, shared_subject_pairs=[(5, 95)])
    caseids = list(cases_df[config.COL_CASEID])
    assignment = models.split_cases(cases_df, caseids)
    assert assignment[5] == assignment[95]


def test_split_cases_is_deterministic():
    cases_df = _toy_cases_df(200)
    caseids = list(cases_df[config.COL_CASEID])
    a = models.split_cases(cases_df, caseids)
    b = models.split_cases(cases_df, caseids)
    assert a == b


def test_split_cases_different_seed_gives_different_split():
    cases_df = _toy_cases_df(200)
    caseids = list(cases_df[config.COL_CASEID])
    a = models.split_cases(cases_df, caseids, seed=1)
    b = models.split_cases(cases_df, caseids, seed=2)
    assert a != b


def test_encode_sex_maps_known_values_and_leaves_unknown_as_nan():
    out = models.encode_sex(pd.Series(["M", "F", "U"]))
    assert out.iloc[0] == 1.0
    assert out.iloc[1] == 0.0
    assert pd.isna(out.iloc[2])
