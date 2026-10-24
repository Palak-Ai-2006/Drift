"""Toy tests for the patient-level split (PLAN.md Section 4: "by caseid
and subject ID if present, 60/20/20, fixed seed")."""

import sys
from pathlib import Path

import numpy as np
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


def test_grouped_kfold_covers_every_caseid_exactly_once():
    cases_df = _toy_cases_df(100)
    caseids = list(cases_df[config.COL_CASEID])
    folds = models.grouped_kfold_by_subject(cases_df, caseids, n_folds=5)
    assert len(folds) == 5
    all_ids = [c for fold in folds for c in fold]
    assert sorted(all_ids) == sorted(caseids)


def test_grouped_kfold_keeps_shared_subject_cases_in_the_same_fold():
    cases_df = _toy_cases_df(100, shared_subject_pairs=[(5, 95)])
    caseids = list(cases_df[config.COL_CASEID])
    folds = models.grouped_kfold_by_subject(cases_df, caseids, n_folds=5)
    fold_of_5 = next(i for i, f in enumerate(folds) if 5 in f)
    fold_of_95 = next(i for i, f in enumerate(folds) if 95 in f)
    assert fold_of_5 == fold_of_95


def test_grouped_kfold_is_reasonably_balanced():
    cases_df = _toy_cases_df(500)
    caseids = list(cases_df[config.COL_CASEID])
    folds = models.grouped_kfold_by_subject(cases_df, caseids, n_folds=5)
    sizes = [len(f) for f in folds]
    assert max(sizes) - min(sizes) <= 5  # one-subject-per-case here, so balance should be tight


def test_grouped_kfold_is_deterministic():
    cases_df = _toy_cases_df(200)
    caseids = list(cases_df[config.COL_CASEID])
    a = models.grouped_kfold_by_subject(cases_df, caseids, n_folds=4)
    b = models.grouped_kfold_by_subject(cases_df, caseids, n_folds=4)
    assert a == b


def test_encode_sex_maps_known_values_and_leaves_unknown_as_nan():
    out = models.encode_sex(pd.Series(["M", "F", "U"]))
    assert out.iloc[0] == 1.0
    assert out.iloc[1] == 0.0
    assert pd.isna(out.iloc[2])


# ---------------------------------------------------------------------------
# OffsetRidgeLogistic (Phase 4 iteration round 3: residual/offset model)
# ---------------------------------------------------------------------------
def _offset_logit(p):
    return np.log(p / (1 - p))


def test_offset_ridge_shrinks_toward_offset_when_extra_features_are_pure_noise():
    rng = np.random.RandomState(0)
    n = 4000
    base_p = rng.uniform(0.05, 0.95, size=n)
    offset = _offset_logit(base_p)
    y = (rng.uniform(size=n) < base_p).astype(float)  # y depends ONLY on offset
    X_extra = rng.normal(size=(n, 5))  # pure noise, unrelated to y

    model = models.OffsetRidgeLogistic(alpha=10.0).fit(X_extra, y, offset)
    # With noise-only extras and a real penalty, coefficients should be small.
    assert np.all(np.abs(model.coef_) < 0.2)

    pred_with_model = model.predict_proba_from_offset(X_extra, offset)
    pred_offset_only = models.OffsetRidgeLogistic._sigmoid(offset)
    assert np.corrcoef(pred_with_model, pred_offset_only)[0, 1] > 0.99


def test_offset_ridge_recovers_real_signal_in_extra_features():
    rng = np.random.RandomState(0)
    n = 4000
    offset = rng.normal(0, 0.3, size=n)  # weak/uninformative offset
    x1 = rng.normal(size=n)
    true_beta = 3.0
    z = offset + true_beta * x1
    p = 1 / (1 + np.exp(-z))
    y = (rng.uniform(size=n) < p).astype(float)
    X_extra = np.column_stack([x1, rng.normal(size=n)])  # x1 informative, 2nd col noise

    model = models.OffsetRidgeLogistic(alpha=0.1).fit(X_extra, y, offset)
    assert model.coef_[0] > 1.0  # recovers a meaningfully positive coefficient on the real signal
    assert abs(model.coef_[1]) < abs(model.coef_[0])  # noise column shrinks more than the real one


def test_fit_offset_ridge_with_inner_cv_runs_and_picks_an_alpha():
    rng = np.random.RandomState(0)
    n = 1000
    groups = rng.randint(0, 100, size=n)
    offset = rng.normal(0, 1, size=n)
    X_extra = rng.normal(size=(n, 3))
    y = (rng.uniform(size=n) < models.OffsetRidgeLogistic._sigmoid(offset)).astype(float)

    model = models.fit_offset_ridge_with_inner_cv(X_extra, y, offset, groups, alphas=(0.1, 1.0, 10.0), n_inner_folds=3)
    assert model.alpha in (0.1, 1.0, 10.0)
    assert model.coef_ is not None and len(model.coef_) == 3
