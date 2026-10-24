"""Patient-level train/val/test split, logistic regression and
HistGradientBoostingClassifier, with calibration.

Phase 4 (PLAN.md Section 4, Phase 4).
Model-selection rule (Oct 24 decision, config.MODEL_SELECT_*): ship the
logistic model unless the boosted model beats it on the VALIDATION set by
both the AUPRC bootstrap-CI bar and the sensitivity-gain bar. Decide on
validation only; never use the test set to pick the model. The logistic
model's coefficients and feature scaling are always saved, since they power
the web demo's "why" panel regardless of which model is shipped for the
headline numbers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from . import config

FEATURE_COLUMNS = (
    "hr", "sbp", "dbp", "map", "pp", "pp_over_sbp", "shock_index",
    "map_std", "map_min", "missing_fraction",
    "hr_slope_5", "hr_slope_10", "hr_slope_15",
    "map_slope_5", "map_slope_10", "map_slope_15",
    "pp_slope_5", "pp_slope_10", "pp_slope_15",
    "shock_index_slope_5", "shock_index_slope_10", "shock_index_slope_15",
    "hr_drift", "map_drift", "pp_drift", "shock_index_drift",
    "age", "asa", "emergency",
)
# sex is categorical (M/F) -- encoded separately, not in the plain-numeric list.


def split_cases(
    cases_df: pd.DataFrame,
    caseids: list[int],
    train_frac: float = config.SPLIT_TRAIN_FRAC,
    val_frac: float = config.SPLIT_VAL_FRAC,
    seed: int = config.RANDOM_SEED,
) -> dict[int, str]:
    """Patient-level 60/20/20 split: groups cases by subjectid first (two
    cases for the same subject always land in the same split -- PLAN.md
    Section 4: "by caseid (and subject ID if present)"), then assigns whole
    subject-groups to train/val/test by a seeded shuffle until each split's
    case-count target is reached. Returns {caseid: "train"|"val"|"test"}.
    """
    subset = cases_df.loc[cases_df[config.COL_CASEID].isin(caseids), [config.COL_CASEID, config.COL_SUBJECTID]]
    groups = subset.groupby(config.COL_SUBJECTID)[config.COL_CASEID].apply(list).to_dict()

    subject_ids = list(groups.keys())
    rng = np.random.RandomState(seed)
    rng.shuffle(subject_ids)

    n_total = len(caseids)
    n_train_target = round(n_total * train_frac)
    n_val_target = round(n_total * val_frac)

    assignment: dict[int, str] = {}
    n_train, n_val = 0, 0
    for sid in subject_ids:
        group_caseids = groups[sid]
        if n_train < n_train_target:
            split = "train"
            n_train += len(group_caseids)
        elif n_val < n_val_target:
            split = "val"
            n_val += len(group_caseids)
        else:
            split = "test"
        for cid in group_caseids:
            assignment[cid] = split
    return assignment


def grouped_kfold_by_subject(
    cases_df: pd.DataFrame,
    caseids: list[int],
    n_folds: int = 5,
    seed: int = config.RANDOM_SEED,
) -> list[list[int]]:
    """n_folds roughly-equal, subject-disjoint partitions of caseids (a
    subject's cases never split across folds, same reasoning as
    split_cases). Used for cross-validated model/feature selection on
    train+val only -- Phase 4 iteration step 1: "your validation set is
    only 88 cases, so choices made on it will be noisy."

    Deterministic greedy balancing: subject-groups are shuffled, then each
    whole group goes to whichever fold currently has the fewest cases
    (ties broken by fold index) -- not a perfect balance when group sizes
    vary, but close, and never splits a subject.
    """
    subset = cases_df.loc[cases_df[config.COL_CASEID].isin(caseids), [config.COL_CASEID, config.COL_SUBJECTID]]
    groups = subset.groupby(config.COL_SUBJECTID)[config.COL_CASEID].apply(list).to_dict()

    subject_ids = list(groups.keys())
    rng = np.random.RandomState(seed)
    rng.shuffle(subject_ids)

    folds: list[list[int]] = [[] for _ in range(n_folds)]
    for sid in subject_ids:
        target_fold = min(range(n_folds), key=lambda i: (len(folds[i]), i))
        folds[target_fold].extend(groups[sid])
    return folds


def encode_sex(sex: pd.Series) -> pd.Series:
    """M -> 1, F -> 0, anything else -> NaN (imputed downstream)."""
    return sex.map({"M": 1.0, "F": 0.0})


def prepare_feature_matrix(windows_df: pd.DataFrame) -> pd.DataFrame:
    X = windows_df[list(FEATURE_COLUMNS)].copy()
    X["sex"] = encode_sex(windows_df["sex"])
    return X


def fit_logistic(X_train: pd.DataFrame, y_train: pd.Series, seed: int = config.RANDOM_SEED) -> Pipeline:
    """Impute (median, train-only) -> standardize (train-only) -> class-weighted
    logistic regression. A Pipeline so val/test transforms always reuse the
    train-fitted imputer/scaler, never refit on val/test (Section 8)."""
    pipeline = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)),
    ])
    pipeline.fit(X_train, y_train)
    return pipeline


def fit_boosted(X_train: pd.DataFrame, y_train: pd.Series, seed: int = config.RANDOM_SEED) -> HistGradientBoostingClassifier:
    """HistGradientBoostingClassifier handles NaN natively -- no imputer needed."""
    clf = HistGradientBoostingClassifier(random_state=seed, class_weight="balanced")
    clf.fit(X_train, y_train)
    return clf


def calibrate_on_validation(fitted_model, X_val: pd.DataFrame, y_val: pd.Series, method: str = "isotonic"):
    """Fit a calibrator on top of an already-trained model, using the
    validation set (never train, never test). sklearn 1.6+ replaced
    CalibratedClassifierCV(cv="prefit") with wrapping the fitted estimator
    in FrozenEstimator so cv has nothing left to refit."""
    calibrated = CalibratedClassifierCV(FrozenEstimator(fitted_model), method=method)
    calibrated.fit(X_val, y_val)
    return calibrated


def logistic_coefficients(pipeline: Pipeline, feature_names: list[str]) -> dict:
    """Coefficients on the STANDARDIZED scale, plus the imputer/scaler
    parameters needed to reproduce the same transform in the web demo's
    'why' panel (Oct 24 decision: logistic always powers this, regardless
    of which model is shipped for headline numbers)."""
    imputer: SimpleImputer = pipeline.named_steps["impute"]
    scaler: StandardScaler = pipeline.named_steps["scale"]
    clf: LogisticRegression = pipeline.named_steps["clf"]
    return {
        "feature_names": list(feature_names),
        "impute_median": imputer.statistics_.tolist(),
        "scale_mean": scaler.mean_.tolist(),
        "scale_std": scaler.scale_.tolist(),
        "coefficients": clf.coef_[0].tolist(),
        "intercept": float(clf.intercept_[0]),
    }
