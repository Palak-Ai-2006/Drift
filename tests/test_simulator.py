"""Phase 5 accept criteria (PLAN.md Section 5): monotonic trends (HR up,
PP down with f; MAP within tolerance until f_c), alert point and MAP<65
point computed for both blunted settings, SYNTHETIC wording defined."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drift import config, simulator  # noqa: E402


@pytest.fixture
def f_grid():
    return np.arange(
        config.SIM_BLOOD_LOSS_FRACTION_MIN,
        config.SIM_BLOOD_LOSS_FRACTION_MAX + config.SIM_BLOOD_LOSS_FRACTION_STEP / 2,
        config.SIM_BLOOD_LOSS_FRACTION_STEP,
    )


def test_hr_rises_monotonically_with_f(f_grid):
    for blunted in (False, True):
        hr = simulator.hr_curve(f_grid, blunted)
        assert np.all(np.diff(hr) >= 0)
        assert hr[-1] > hr[0]


def test_pp_narrows_monotonically_with_f(f_grid):
    pp = simulator.pp_curve(f_grid)
    assert np.all(np.diff(pp) <= 0)
    assert pp[-1] < pp[0]


def test_map_holds_within_tolerance_until_compensation_limit(f_grid):
    map_ = simulator.map_curve(f_grid)
    f_c = config.SIM_COMPENSATION_LIMIT_FRACTION_DEFAULT
    at_fc = map_[np.argmin(np.abs(f_grid - f_c))]
    assert abs(at_fc - simulator.MAP0) < 10.0  # "holds within a few mmHg" -- loose, illustrative tolerance


def test_map_falls_after_compensation_limit(f_grid):
    map_ = simulator.map_curve(f_grid)
    assert np.all(np.diff(map_) <= 1e-9)  # never rises
    assert map_[-1] < map_[0] - 20  # meaningfully lower by max blood loss


def test_blunted_response_dampens_hr_rise(f_grid):
    hr_normal = simulator.hr_curve(f_grid, blunted=False)
    hr_blunted = simulator.hr_curve(f_grid, blunted=True)
    assert np.all(hr_blunted[1:] < hr_normal[1:])  # strictly less HR rise once f > 0


def test_blunted_response_delays_or_removes_the_alert_point(f_grid):
    curves_normal = simulator.compute_curves(f_grid, blunted=False)
    curves_blunted = simulator.compute_curves(f_grid, blunted=True)
    pts_normal = simulator.alert_and_map65_points(f_grid, curves_normal)
    pts_blunted = simulator.alert_and_map65_points(f_grid, curves_blunted)
    assert pts_normal["alert_f"] is not None
    assert pts_blunted["alert_f"] is None or pts_blunted["alert_f"] > pts_normal["alert_f"]


def test_alert_and_map65_points_computed_for_both_blunted_settings(f_grid, capsys):
    for blunted in (False, True):
        curves = simulator.compute_curves(f_grid, blunted)
        pts = simulator.alert_and_map65_points(f_grid, curves)
        print(f"blunted={blunted}: {pts}")  # Phase 5 accept: "printed for both settings"
        assert "alert_f" in pts and "map_below_65_f" in pts
    captured = capsys.readouterr()
    assert "blunted=False" in captured.out
    assert "blunted=True" in captured.out


def test_sbp_dbp_derived_consistently_from_map_and_pp(f_grid):
    curves = simulator.compute_curves(f_grid, blunted=False)
    expected_sbp = curves["map"] + config.SIM_SBP_FROM_MAP_PP_COEF * curves["pp"]
    expected_dbp = curves["map"] - config.SIM_DBP_FROM_MAP_PP_COEF * curves["pp"]
    assert np.allclose(curves["sbp"], expected_sbp)
    assert np.allclose(curves["dbp"], expected_dbp)


def test_drift_rule_score_is_clamped_0_to_100():
    hr = np.array([0.0, 72.0, 500.0])
    pp = np.array([100.0, 42.0, -50.0])
    score = simulator.drift_rule_score(hr, pp)
    assert np.all(score >= 0.0) and np.all(score <= 100.0)


def test_build_sim_export_includes_disclaimer_and_meta():
    export = simulator.build_sim_export()
    assert "not confirmed in our data" in export["meta"]["disclaimer"].lower()
    assert export["meta"]["f_c"] == config.SIM_COMPENSATION_LIMIT_FRACTION_DEFAULT
    assert len(export["f"]) == len(export["blunted_false"]["hr"]) == len(export["blunted_true"]["hr"])


def test_write_sim_curves_js_produces_loadable_js(tmp_path):
    dest = tmp_path / "sim_curves.js"
    simulator.write_sim_curves_js(dest)
    text = dest.read_text()
    assert text.startswith("window.DRIFT_SIM = ")
    json_part = text[len("window.DRIFT_SIM = "):].rstrip().rstrip(";")
    parsed = json.loads(json_part)
    assert "f" in parsed and "blunted_false" in parsed and "blunted_true" in parsed
