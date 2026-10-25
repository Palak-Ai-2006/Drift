#!/usr/bin/env python
"""Round 4: train and evaluate on semi-synthetic bleeds (SYNTHETIC_PLAN.md 5, 5a).

  --stage dev   Build synth-train and synth-val, train candidates on train,
                choose + calibrate + set thresholds on val. Never builds or
                looks at synth-test.
  --stage test  Evaluate the saved choice on synth-test and the shifted test
                set, ONCE. A second run is refused unless --rerun-reason is
                given; the reason is logged into metrics_synth.json.

Both stages refuse to run if the generator no longer matches the freeze
fingerprint in artifacts/round4_generator_freeze.json.
Every number is a SIMULATION result.
"""

import argparse
import datetime
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, metrics, models, semisynth, semisynth_eval as se, vitaldb_io  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts"
FREEZE = ART / "round4_generator_freeze.json"
MODEL_PATH = ART / "round4_model.joblib"
DEV_JSON = ART / "round4_dev_results.json"
METRICS_JSON = ART / "metrics_synth.json"
STAMP = ART / "round4_test_evaluated.json"
MISSES_CSV = ART / "round4_test_misses.csv"
WINDOWS_PARQUET = ROOT / "data" / "processed" / "windows.parquet"
HOLDOUT_CSV = ROOT / "data" / "interim" / "fresh_holdout_selection.csv"
ID_OFFSET = {"train": 0, "val": 100_000, "test": 200_000, "test_shifted": 300_000}
H = config.SYNTH_EVAL_HORIZON_MIN
NO_COLLAPSE = config.SYNTH_LABEL_BLEED_NO_COLLAPSE
COLLAPSE = config.SYNTH_LABEL_BLEED_COLLAPSE


def verify_freeze():
    frozen = json.loads(FREEZE.read_text())
    now = se.generator_fingerprint()
    for k, v in now.items():
        if frozen[k] != v:
            raise SystemExit(f"Generator changed since freeze ({k}). Refusing to run -- see SYNTHETIC_PLAN.md Section 4.2.")
    print(f"Generator matches freeze from {frozen['frozen_at']}.")


def split_windows(splits_needed):
    cases_df = vitaldb_io.load_case_table()
    windows_df = pd.read_parquet(WINDOWS_PARQUET, columns=[config.COL_CASEID])
    all_ids = set(windows_df[config.COL_CASEID])
    pool = semisynth.get_baseline_pool_caseids(cases_df, windows_df)
    forbidden = (all_ids - set(pool)) | set(pd.read_csv(HOLDOUT_CSV)[config.COL_CASEID])
    split = semisynth.split_baseline_cases(cases_df, pool)
    out = {}
    for name in ("train", "val", "test"):  # always draw all three so a split's windows never depend on which stage runs
        rng = np.random.RandomState(config.SYNTH_EVAL_WINDOW_SEEDS[name])
        wins = []
        for cid in sorted(c for c in pool if split[c] == name):
            row = cases_df.loc[cases_df[config.COL_CASEID] == cid].iloc[0]
            w = semisynth.select_baseline_segment(
                vitaldb_io.load_and_clean_case(int(cid)), vitaldb_io.load_drug_tracks(int(cid)),
                float(row[config.COL_OPSTART]), float(row[config.COL_OPEND]), rng,
            )
            if w is not None:
                wins.append((int(cid), w))
        out[name] = wins
    se.check_split_disjoint(out, forbidden)
    print("Baseline windows: " + ", ".join(f"{k}={len(v)}" for k, v in out.items())
          + f" (source cases disjoint; none from Phase 4 test or fresh holdout: {len(forbidden)} forbidden)")
    return {k: v for k, v in out.items() if k in splits_needed}


def featurize(cases, offset):
    jobs = [(c, offset + i) for i, c in enumerate(cases)]
    for c, sid in jobs:
        c.meta["synth_id"] = sid
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(se.featurize_one, jobs, chunksize=16))
    rows = pd.concat([r for _, r, _ in results if not r.empty], ignore_index=True)
    events = {sid: ev for sid, _, ev in results}
    meta = {c.meta["synth_id"]: c.meta for c in cases}
    return rows, events, meta


def collapse_events(meta, events, sids):
    """First primary event of each bleed_collapse stream (the collapse)."""
    return {sid: [events[sid][0]] for sid in sids if meta[sid]["label"] == COLLAPSE and events[sid]}


def sens_and_leads(arrays, cevents, thr):
    leads, n = [], 0
    for sid, ev in cevents.items():
        n += 1
        lead = se.detection(se.fast_alerts(arrays[sid], thr), ev[0]) if sid in arrays else None
        if lead is not None:
            leads.append(lead)
    return (len(leads) / n if n else float("nan")), leads


def predict_raw(model, X):
    return model.predict_proba(X)[:, 1]


# ---------------------------------------------------------------------------
def stage_dev():
    verify_freeze()
    wins = split_windows({"train", "val"})
    data = {}
    for name in ("train", "val"):
        cases = se.build_cases(wins[name], config.SYNTH_EVAL_CASE_SEEDS[name])
        rows, events, meta = featurize(cases, ID_OFFSET[name])
        rows = rows[rows["label"] != NO_COLLAPSE].reset_index(drop=True)
        data[name] = (rows, events, meta)
        labs = pd.Series([m["label"] for m in meta.values()]).value_counts().to_dict()
        print(f"{name}: {len(cases)} streams {labs}; scored rows {len(rows)}")

    tr_rows, _, _ = data["train"]
    va_rows, va_events, va_meta = data["val"]
    lab = f"label_h{int(H)}"
    fit = tr_rows[tr_rows[lab].notna()]
    X_fit, y_fit = se.feature_matrix(fit), fit[lab]
    print(f"Training rows with known label: {len(fit)} (positive rate {y_fit.mean():.4f})")

    fitted = {"logistic": models.fit_logistic(X_fit, y_fit), "boosted": models.fit_boosted(X_fit, y_fit)}
    va_sids = sorted(va_rows["synth_id"].unique())
    cev = collapse_events(va_meta, va_events, va_sids)
    X_va = se.feature_matrix(va_rows)

    selection = {}
    for name in config.SYNTH_MODEL_CANDIDATES:
        va_rows[f"{name}_raw"] = predict_raw(fitted[name], X_va)
        arr = se.case_arrays(va_rows, f"{name}_raw")
        thr, fa = se.threshold_for_fa(arr, va_events, config.SYNTH_EVAL_PRIMARY_FA)
        sens, leads = sens_and_leads(arr, cev, thr)
        selection[name] = {"val_sensitivity": sens, "val_fa": fa, "val_median_lead_min": float(np.median(leads)) / 60 if leads else float("nan")}
        print(f"  {name}: val sens@1FA/hr={sens:.3f} (FA {fa:.2f}/hr), median lead {selection[name]['val_median_lead_min']:.1f} min")

    a, b = selection["logistic"], selection["boosted"]
    gap_pp = (b["val_sensitivity"] - a["val_sensitivity"]) * 100
    if abs(gap_pp) > config.SYNTH_MODEL_SELECT_TIE_PP:
        chosen = "boosted" if gap_pp > 0 else "logistic"
        why = f"sensitivity gap {gap_pp:+.1f} pp"
    else:
        lead_gap = b["val_median_lead_min"] - a["val_median_lead_min"]
        if abs(lead_gap) > config.SYNTH_MODEL_SELECT_LEAD_TIE_MIN:
            chosen = "boosted" if lead_gap > 0 else "logistic"
            why = f"sensitivity within {config.SYNTH_MODEL_SELECT_TIE_PP} pp; lead gap {lead_gap:+.2f} min"
        else:
            chosen, why = "logistic", "tied on sensitivity and lead -> simpler model"
    print(f"=> chosen: {chosen} ({why})")

    va_fit = va_rows[va_rows[lab].notna()]
    calibrated = models.calibrate_on_validation(fitted[chosen], se.feature_matrix(va_fit), va_fit[lab])
    va_rows["model_risk"] = calibrated.predict_proba(X_va)[:, 1]

    thresholds = {}
    for method, col in (("model", "model_risk"), ("b2", "b2_risk")):
        arr = se.case_arrays(va_rows, col)
        thresholds[method] = {}
        for target in config.SYNTH_EVAL_FA_TARGETS:
            thr, fa = se.threshold_for_fa(arr, va_events, target)
            sens, leads = sens_and_leads(arr, cev, thr)
            thresholds[method][str(target)] = {"threshold": thr, "val_fa": fa, "val_sensitivity": sens,
                                               "val_median_lead_min": float(np.median(leads)) / 60 if leads else None}
            print(f"  {method} @ {target} FA/hr: thr={thr:.4f}, val sens={sens:.3f}, FA={fa:.2f}/hr, "
                  f"lead {thresholds[method][str(target)]['val_median_lead_min']}")
    print(f"  (B2 at 1 FA/hr = alarm when MAP < {-thresholds['b2']['1.0']['threshold']:.1f} mmHg)")

    coef = models.logistic_coefficients(fitted["logistic"], list(config.SYNTH_FEATURE_COLUMNS))
    joblib.dump({"chosen": chosen, "calibrated": calibrated, "thresholds": thresholds}, MODEL_PATH)
    DEV_JSON.write_text(json.dumps({
        "chosen_model": chosen, "selection_reason": why, "selection": selection, "thresholds": thresholds,
        "n_train_rows_fit": int(len(fit)), "train_positive_rate": float(y_fit.mean()),
        "logistic_coefficients": coef, "note": "Validation-stage results only. SIMULATION.",
    }, indent=2, default=float))
    print(f"Saved {MODEL_PATH.name}, {DEV_JSON.name}")


# ---------------------------------------------------------------------------
def per_case_summary(arrays_by_method, events, meta, thresholds):
    """For each scored stream and method: alerts, collapse lead, false alarms."""
    out = {}
    for sid, m in meta.items():
        if m["label"] == NO_COLLAPSE or sid not in arrays_by_method["model"]:
            continue
        hours = len(arrays_by_method["model"][sid][0]) * config.PREDICTION_STRIDE_MIN / 60.0
        ev = events[sid]
        collapse_s = ev[0] if (m["label"] == COLLAPSE and ev) else None
        onset_s = m["t0_min"] * 60.0 if m["is_bleed"] else None
        rec = {"hours": hours, "collapse_s": collapse_s, "source": m["source_caseid"], "tier": m["tier"]}
        for method, thr in thresholds.items():
            al = se.fast_alerts(arrays_by_method[method.split("@")[0]][sid], thr)
            rec[method] = {
                "lead": se.detection(al, collapse_s) if collapse_s is not None else None,
                "false": se.n_false(al, ev), "false_bleed_aware": se.bleed_aware_false_alarms(al, ev, onset_s),
                "alerts": al,
            }
        out[sid] = rec
    return out


def summarize(recs, method):
    n_ev = sum(r["collapse_s"] is not None for r in recs)
    leads = [r[method]["lead"] for r in recs if r["collapse_s"] is not None and r[method]["lead"] is not None]
    hours = sum(r["hours"] for r in recs)
    return {
        "n_collapses": n_ev, "n_detected": len(leads),
        "sensitivity": len(leads) / n_ev if n_ev else None,
        "fa_per_hour": sum(r[method]["false"] for r in recs) / hours if hours else None,
        "fa_per_hour_bleed_aware": sum(r[method]["false_bleed_aware"] for r in recs) / hours if hours else None,
        "lead_time": {k: (v / 60.0 if isinstance(v, float) else v) for k, v in metrics.lead_time_summary(leads).items()},
        "monitored_hours": hours,
    }


def bootstrap(recs, method, n=config.BOOTSTRAP_N_RESAMPLES):
    by_src = {}
    for r in recs:
        by_src.setdefault(r["source"], []).append(r)
    srcs = sorted(by_src)
    rng = np.random.RandomState(config.RANDOM_SEED)
    sens, fas = [], []
    for _ in range(n):
        sample = [rr for s in rng.choice(srcs, size=len(srcs), replace=True) for rr in by_src[s]]
        s = summarize(sample, method)
        if s["sensitivity"] is not None:
            sens.append(s["sensitivity"])
        fas.append(s["fa_per_hour"])
    q = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] if v else [None, None]
    return {"sensitivity_ci95": q(sens), "fa_per_hour_ci95": q(fas), "n_source_cases": len(srcs)}


def std_monitor(recs):
    """B1 OR HR>120 OR SBP<90. Always 'detects' a collapse (its MAP<65 part
    fires at the event); lead = earlier HR/SBP alert within H, else 0."""
    n_ev, leads = 0, []
    for r in recs:
        if r["collapse_s"] is not None:
            n_ev += 1
            leads.append(r["std"]["lead"] or 0.0)
    hours = sum(r["hours"] for r in recs)
    return {
        "n_collapses": n_ev, "sensitivity": 1.0 if n_ev else None,
        "fa_per_hour": sum(r["std"]["false"] for r in recs) / hours if hours else None,
        "fa_per_hour_bleed_aware": sum(r["std"]["false_bleed_aware"] for r in recs) / hours if hours else None,
        "lead_time": {k: (v / 60.0 if isinstance(v, float) else v) for k, v in metrics.lead_time_summary(leads).items()},
        "note": "MAP<65 OR HR>120 OR SBP<90; typical settings, not a verified factory default.",
    }


def evaluate_set(rows, events, meta, model_bundle, label):
    X = se.feature_matrix(rows)
    rows = rows.copy()
    rows["model_risk"] = model_bundle["calibrated"].predict_proba(X)[:, 1]
    arrays = {"model": se.case_arrays(rows, "model_risk"), "b2": se.case_arrays(rows, "b2_risk"),
              "std": se.case_arrays(rows, "std_risk")}
    thr = {f"model@{t}": model_bundle["thresholds"]["model"][str(t)]["threshold"] for t in config.SYNTH_EVAL_FA_TARGETS}
    thr.update({f"b2@{t}": model_bundle["thresholds"]["b2"][str(t)]["threshold"] for t in config.SYNTH_EVAL_FA_TARGETS})
    thr["std"] = 0.5
    recs = per_case_summary(arrays, events, meta, thr)

    lab = f"label_h{int(H)}"
    result = {"per_tier": {}}
    misses = []
    for tier in list(config.SYNTH_TIERS) + ["ALL"]:
        tr = [r for r in recs.values() if tier == "ALL" or r["tier"] == tier]
        tier_rows = rows if tier == "ALL" else rows[rows["tier"] == tier]
        res = {"B1_map_below_65": {"sensitivity": 1.0, "lead_time_median_min": 0.0, "fa_per_hour": 0.0,
                                   "n_collapses": sum(r["collapse_s"] is not None for r in tr)},
               "standard_monitor": std_monitor(tr)}
        for t in config.SYNTH_EVAL_FA_TARGETS:
            res[f"model@{t}FA"] = summarize(tr, f"model@{t}")
            res[f"b2@{t}FA"] = summarize(tr, f"b2@{t}")
        res["model@1.0FA"]["bootstrap"] = bootstrap(tr, "model@1.0")
        res["b2@1.0FA"]["bootstrap"] = bootstrap(tr, "b2@1.0")
        paired = [(r["model@1.0"]["lead"] - (r["std"]["lead"] or 0.0)) / 60.0
                  for r in tr if r["collapse_s"] is not None and r["model@1.0"]["lead"] is not None]
        res["model_minus_standard_monitor_lead_min_median"] = float(np.median(paired)) if paired else None
        res["secondary_auroc_auprc_brier"] = metrics.auroc_auprc_brier(tier_rows[lab], tier_rows["model_risk"])
        result["per_tier"][tier] = res

    for sid, r in recs.items():
        if r["collapse_s"] is not None and r["model@1.0"]["lead"] is None:
            m = meta[sid]
            misses.append({"set": label, "synth_id": sid, "tier": m["tier"], "source_caseid": m["source_caseid"],
                           "cause": se.classify_miss(m, r["collapse_s"]), "rate_band": m["rate_band"],
                           "g_hr": round(m["g_hr"], 3), "collapse_min": round(r["collapse_s"] / 60, 1),
                           "artifact": m.get("artifact"), "stim_onset_min": m.get("stim_onset_min"),
                           "b2_detected": r["b2@1.0"]["lead"] is not None})

    # Non-bleed hypotension (T4 negatives that crossed 65): descriptive.
    nbh = [sid for sid, m in meta.items() if m["label"] == "non_bleed_hypotension" and events[sid] and sid in recs]
    nbh_leads = [se.detection(recs[s]["model@1.0"]["alerts"], events[s][0]) for s in nbh]
    result["non_bleed_hypotension_descriptive"] = {
        "n_events": len(nbh), "n_detected_model@1FA": sum(x is not None for x in nbh_leads),
        "median_lead_min": float(np.median([x for x in nbh_leads if x is not None])) / 60 if any(x is not None for x in nbh_leads) else None,
        "note": "No HR/PP precursor by design; early warning is not expected.",
    }

    # bleed_no_collapse: descriptive only (rows were featurized but never scored).
    result["bleed_no_collapse_descriptive"] = describe_no_collapse(rows, meta, model_bundle)
    result["reliability_all"] = metrics.reliability_curve(rows[lab], rows["model_risk"])
    return result, misses, rows


def describe_no_collapse(rows, meta, bundle):
    nc = rows[rows["label"] == NO_COLLAPSE].copy()
    if nc.empty:
        return {"n_streams": 0}
    t0 = nc["synth_id"].map(lambda s: meta[s]["t0_min"])
    rate = nc["synth_id"].map(lambda s: meta[s]["rate_frac_per_min"])
    f = np.clip((nc["t_s"] / 60.0 - t0).clip(lower=0) * rate, 0, config.SYNTH_F_MAX)
    bins = pd.cut(f, [-1e-9, 0.0, 0.1, 0.2, 1.0], labels=["before onset", "0-10% lost", "10-20% lost", ">20% lost"])
    by_bin = nc.groupby(bins, observed=False)["model_risk"].median().to_dict()
    thr = bundle["thresholds"]["model"]["1.0"]["threshold"]
    alerted_after = alerted_before = 0
    streams = nc["synth_id"].unique()
    for sid in streams:
        g = nc[nc["synth_id"] == sid]
        al = se.fast_alerts(se.case_arrays(g, "model_risk")[sid], thr)
        on = meta[sid]["t0_min"] * 60.0
        alerted_after += any(a >= on for a in al)
        alerted_before += any(a < on for a in al)
    return {
        "n_streams": int(len(streams)),
        "median_risk_by_blood_loss": {str(k): (None if pd.isna(v) else float(v)) for k, v in by_bin.items()},
        "fraction_alerted_after_onset_at_1FA": alerted_after / len(streams),
        "fraction_alerted_before_onset_at_1FA": alerted_before / len(streams),
        "note": "Descriptive only, not graded. Bleed underway, MAP never < 65 in window.",
    }


def stage_test(rerun_reason):
    verify_freeze()
    if STAMP.exists() and not rerun_reason:
        raise SystemExit(f"Test set already evaluated ({json.loads(STAMP.read_text())['at']}). "
                         "Re-running needs --rerun-reason, which is logged.")
    bundle = joblib.load(MODEL_PATH)
    wins = split_windows({"test"})["test"]
    output = {"SIMULATION": True, "chosen_model": bundle["chosen"], "horizon_min": H,
              "thresholds_from_val": bundle["thresholds"], "sets": {}}
    all_misses = []
    for label, shifted in (("test", False), ("test_shifted", True)):
        cases = se.build_cases(wins, config.SYNTH_EVAL_CASE_SEEDS[label], shifted=shifted)
        rows, events, meta = featurize(cases, ID_OFFSET[label])
        counts = pd.Series([m["label"] for m in meta.values()]).value_counts().to_dict()
        res, misses, scored_rows = evaluate_set(rows, events, meta, bundle, label)
        res["stream_counts"] = counts
        output["sets"][label] = res
        all_misses += misses
        print_table(label, res)
        if label == "test":
            plot_reliability(res["reliability_all"], bundle["chosen"])

    t1t2 = {}
    for tier in config.SYNTH_EVAL_TARGET_TIERS:
        r = output["sets"]["test"]["per_tier"][tier]["model@1.0FA"]
        met = r["sensitivity"] is not None and r["sensitivity"] >= config.SYNTH_EVAL_TARGET_SENSITIVITY \
            and r["fa_per_hour"] <= config.SYNTH_EVAL_PRIMARY_FA
        t1t2[tier] = {"sensitivity": r["sensitivity"], "fa_per_hour": r["fa_per_hour"], "target_met": bool(met)}
    output["preregistered_target_check"] = t1t2
    output["misses_by_cause"] = pd.Series([m["cause"] for m in all_misses if m["set"] == "test"]).value_counts().to_dict()
    output["rerun_reason"] = rerun_reason
    pd.DataFrame(all_misses).to_csv(MISSES_CSV, index=False)
    METRICS_JSON.write_text(json.dumps(output, indent=2, default=lambda x: None if x is None else float(x)))
    STAMP.write_text(json.dumps({"at": datetime.datetime.now().isoformat(timespec="seconds"), "rerun_reason": rerun_reason}))
    print(f"\nTarget check (T1, T2 at 1 FA/hr): {t1t2}")
    print(f"Misses by cause (test): {output['misses_by_cause']}")
    print(f"Saved {METRICS_JSON.name}, {MISSES_CSV.name}")


def print_table(label, res):
    print(f"\n=== {label} (SIMULATION) ===")
    print(f"{'tier':5} {'n':>4} | {'model sens':>10} {'FA/h':>5} {'lead':>5} | {'B2 sens':>7} {'FA/h':>5} {'lead':>5} | {'std FA/h':>8} {'lead':>5}")
    for tier, r in res["per_tier"].items():
        m, b, s = r["model@1.0FA"], r["b2@1.0FA"], r["standard_monitor"]
        fmt = lambda v, p=3: "  n/a" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{p}f}"
        print(f"{tier:5} {m['n_collapses']:>4} | {fmt(m['sensitivity']):>10} {fmt(m['fa_per_hour'], 2):>5} "
              f"{fmt(m['lead_time']['median_s'], 1):>5} | {fmt(b['sensitivity']):>7} {fmt(b['fa_per_hour'], 2):>5} "
              f"{fmt(b['lead_time']['median_s'], 1):>5} | {fmt(s['fa_per_hour'], 2):>8} {fmt(s['lead_time']['median_s'], 1):>5}")


def plot_reliability(rel, name):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    bins = [b for b in rel["bins"] if b["n"] > 0]
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="#9BA7B4")
    ax.plot([b["mean_predicted"] for b in bins], [b["observed_fraction"] for b in bins], "o-", color=config.WEB_COLOR_TRACE_MAP)
    ax.set_xlabel("Mean predicted risk")
    ax.set_ylabel("Observed fraction with collapse in 15 min")
    ax.set_title(f"SIMULATION: calibration on synth-test ({name})", fontsize=9)
    fig.tight_layout()
    fig.savefig(ART / "round4_reliability_plot.png", dpi=120)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=("dev", "test"), required=True)
    p.add_argument("--rerun-reason", default=None)
    a = p.parse_args()
    stage_dev() if a.stage == "dev" else stage_test(a.rerun_reason)
