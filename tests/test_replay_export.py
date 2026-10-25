"""Phase 7 required test: replay-export causality (Adjustment A3), plus the
replay data schema the web page relies on.

The causality test re-derives exported risk from VitalDB data truncated at
each timestamp. It needs the local (gitignored) data/ folder, so it skips
cleanly where that data isn't present.
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from drift import config  # noqa: E402

REPLAY_JS = ROOT / "web" / "data" / "replay_cases.js"
KINDS = {"best", "typical", "miss", "false_alarm", "insufficient"}


def _cases():
    text = REPLAY_JS.read_text()
    return json.loads(text[text.index("=") + 1:].rstrip().rstrip(";"))


def test_replay_cases_schema():
    cases = _cases()
    assert cases
    kinds = {c["kind"] for c in cases}
    assert {"miss", "false_alarm"} <= kinds  # Adjustment A4: failures shown, not only wins
    assert kinds <= KINDS
    for c in cases:
        n = len(c["t"])
        for key in ("hr", "sbp", "dbp", "map", "pp", "si", "missing"):
            assert len(c[key]) == n, f"{c['id']}: {key} length"
        assert np.all(np.diff(c["t"]) > 0)
        assert len(c["risk_t"]) == len(c["risk"])
        assert all(0.0 <= r <= 1.0 for r in c["risk"])
        # Risk sits on the per-minute prediction grid, the excerpt on the 30-s
        # sample grid, so edge points can fall up to one sample interval outside.
        slack = config.REPLAY_EXPORT_RESOLUTION_S
        assert all(c["t"][0] - slack <= rt <= c["t"][-1] + slack for rt in c["risk_t"]), f"{c['id']}: risk outside excerpt"
        assert isinstance(c["verdict"], str) and c["verdict"]
        if c["kind"] == "miss":
            assert c["alert_t"] is None
        for key in ("alert_t", "standard_alarm_t", "event_t"):
            if c[key] is not None:
                assert c["t"][0] <= c[key] <= c["t"][-1] + config.REPLAY_EXPORT_RESOLUTION_S


@pytest.mark.skipif(not (ROOT / "data" / "processed" / "windows.parquet").exists(),
                    reason="needs local VitalDB data (gitignored data/ folder)")
def test_exported_replay_risk_is_causal():
    """Every sampled exported risk equals the risk recomputed from data
    truncated at its own timestamp -- the same check as
    scripts/06b_replay_causality_check.py, as a test."""
    spec = importlib.util.spec_from_file_location("causality", ROOT / "scripts" / "06b_replay_causality_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from drift import vitaldb_io

    calibrated = mod.refit_shipped_model(vitaldb_io.load_case_table())
    samples = [(c["caseid"], t, r) for c in _cases() for t, r in zip(c["risk_t"], c["risk"])]
    rng = np.random.RandomState(config.RANDOM_SEED)
    idx = rng.choice(len(samples), size=min(mod.N_CHECK, len(samples)), replace=False)
    for caseid, t, exported in (samples[i] for i in idx):
        cleaned = vitaldb_io.load_and_clean_case(int(caseid))
        truncated = cleaned[cleaned["Time"] <= t].sort_values("Time")
        map_at_t = truncated.iloc[-1][config.TRACK_MAP]
        recomputed = float(calibrated.predict_proba(pd.DataFrame({"map": [map_at_t]}))[:, 1][0])
        assert round(recomputed, 4) == pytest.approx(exported, abs=1e-9), f"case {caseid} t={t}"
