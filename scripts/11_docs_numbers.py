#!/usr/bin/env python
"""Phase 7: fill the generated-number blocks in README.md, DEVPOST.md and
VIDEO_SCRIPT.md from web/data/proof.js and web/data/replay_cases.js (which
are themselves generated from artifacts/*.json). Text between
<!-- NUMBERS:<name>:START --> and <!-- NUMBERS:<name>:END --> is replaced;
everything else in those files is prose with no results numbers in it
(CLAUDE.md Section 12: no number typed by hand).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_js(path: Path):
    text = path.read_text()
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


def pct(x):
    return f"{100 * x:.1f}%"


def real_table(proof):
    lines = ["| Method (real surgical data, test set) | Sensitivity | Median lead | False alarms / patient-hour |", "|---|---|---|---|"]
    for r in proof["operating_points_table"]:
        lines.append(f"| {r['method']} | {pct(r['sensitivity'])} | {r['lead_time_median_s'] / 60:.1f} min | {r['fa_per_hour']:.2f} |")
    return "\n".join(lines)


def sim_table(sim):
    lines = ["| Tier (simulation) | Bleeds that collapsed | Sensitivity [95% CI] | False alarms / hr | Lead: model | Lead: MAP cutoff | Lead: standard monitor |",
             "|---|---|---|---|---|---|---|"]
    for r in sim["rows"]:
        lo, hi = r["model_sensitivity_ci95"]
        lines.append(f"| {r['tier']} | {r['n_collapses']} | {pct(r['model_sensitivity'])} [{pct(lo)}–{pct(hi)}] | {r['model_fa_per_hour']:.2f} "
                     f"| {r['model_lead_median_min']:.1f} min | {r['b2_lead_median_min']:.1f} min | {r['standard_monitor_lead_median_min']:.1f} min |")
    return "\n".join(lines)


def blocks():
    proof = load_js(ROOT / "web" / "data" / "proof.js")
    cases = load_js(ROOT / "web" / "data" / "replay_cases.js")
    sim = proof["simulation_round4"]
    by_method = {r["method"]: r for r in proof["operating_points_table"]}
    model = next(r for m, r in by_method.items() if "(shipped model" in m)
    b2 = next(r for m, r in by_method.items() if m.startswith("B2"))
    holdout = next(r for m, r in by_method.items() if "holdout" in m)
    all_tiers = next(r for r in sim["rows"] if r["tier"] == "All tiers")
    best = next(c for c in cases if c["kind"] == "best")
    best_lead = (best["standard_alarm_t"] - best["alert_t"]) / 60
    t1, t2 = sim["target_check"]["T1"], sim["target_check"]["T2"]

    results = f"""### Real surgical data (VitalDB)
{real_table(proof)}

Calibration (shipped model, test set): Brier {proof['brier_score']:.3f}, AUROC {proof['auroc']:.3f}.

### Simulation (real baselines + injected bleeds; synthetic)
{sim_table(sim)}

Pre-registered target (≥ {pct(sim['target_sensitivity'])} at ≤ 1 false alarm/hr on T1 and T2): T1 {pct(t1['sensitivity'])} at {t1['fa_per_hour']:.2f}/hr, T2 {pct(t2['sensitivity'])} at {t2['fa_per_hour']:.2f}/hr, both met on the point estimate (lower CI bounds are below the target). Unseen bleed settings, all tiers: {pct(sim['shifted_all']['sensitivity'])} at {sim['shifted_all']['fa_per_hour']:.2f}/hr."""

    claim = (f"On real surgical data, the shipped early alert caught {pct(model['sensitivity'])} of low-pressure events a median "
             f"{model['lead_time_median_s'] / 60:.1f} min early at {model['fa_per_hour']:.2f} false alarms per patient-hour "
             f"({pct(holdout['sensitivity'])} on a never-touched holdout), about the same as a tuned MAP cutoff "
             f"({pct(b2['sensitivity'])}, {b2['lead_time_median_s'] / 60:.1f} min). In simulation, heart-rate and pulse-pressure "
             f"trends warned a median {all_tiers['model_lead_median_min']:.1f} min before collapse versus "
             f"{all_tiers['b2_lead_median_min']:.1f} min for a MAP cutoff, at {all_tiers['model_fa_per_hour']:.2f} vs "
             f"{all_tiers['b2_fa_per_hour']:.2f} false alarms per hour.")

    video = (f"- Replay, best example: the early alert fires {best_lead:.1f} min before the standard alarm.\n"
             f"- Real test set: {pct(model['sensitivity'])} of events caught, median {model['lead_time_median_s'] / 60:.1f} min early, "
             f"{model['fa_per_hour']:.2f} false alarms per patient-hour; a plain MAP cutoff does about the same "
             f"({pct(b2['sensitivity'])}, {b2['lead_time_median_s'] / 60:.1f} min).\n"
             f"- Simulation: {pct(all_tiers['model_sensitivity'])} of collapses caught at {all_tiers['model_fa_per_hour']:.2f} false alarms/hr, "
             f"median {all_tiers['model_lead_median_min']:.1f} min warning vs {all_tiers['b2_lead_median_min']:.1f} min for a MAP cutoff "
             f"and {all_tiers['standard_monitor_lead_median_min']:.1f} min for a standard monitor.")
    return {"RESULTS": results, "CLAIM": claim, "VIDEO": video}


def fill(path: Path, values: dict):
    text = path.read_text()
    for name, body in values.items():
        pattern = re.compile(rf"(<!-- NUMBERS:{name}:START -->)(.*?)(<!-- NUMBERS:{name}:END -->)", re.S)
        text = pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(3)}", text)
    path.write_text(text)
    print(f"Filled {path.name}")


if __name__ == "__main__":
    v = blocks()
    for name in ("README.md", "DEVPOST.md", "VIDEO_SCRIPT.md"):
        fill(ROOT / name, v)
