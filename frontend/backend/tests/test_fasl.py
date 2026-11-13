import json
from pathlib import Path

import pytest

from cmn_frontend import fasl

CASES = json.loads((Path(__file__).resolve().parents[2] / "shared" / "gate_cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES)
def test_shared_gate_cases(case):
    assert fasl.gate_present_rolling(case["L"], case["theta"], case["N"], case["M"]) == case["present"]


def test_episode_needs_core_and_five():
    params = fasl.GateParams(theta=0.6, need_days=1, window=1, core=("C2",))
    five_no_core = {c: [True] for c in ["C1", "C3", "C4", "C5", "C6"]}
    assert fasl.episode_flags(five_no_core, params) == [False]
    assert fasl.episode_flags({**five_no_core, "C2": [True]}, params) == [True]
    four_with_core = {c: [True] for c in ["C1", "C2", "C4", "C8"]}
    assert fasl.episode_flags(four_with_core, params) == [False]


def test_score_days_unconfigured_is_none(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"M": 14, "N": 6, "theta": 0.6, "core_symptoms": ["C2"], "C3": {},
                             "C1": {"a": {"w": 0.5, "mf": {"type": "tri", "lo": 0, "mid": 1, "hi": 1}},
                                    "b": {"w": 0.5, "mf": {"type": "tri", "lo": 0, "mid": 1, "hi": 1,
                                                           "invert": True}}}}))
    cfg = fasl.load_config(p)
    assert (cfg.M, cfg.N, cfg.theta, cfg.core) == (14, 6, 0.6, ["C2"])
    out = fasl.score_days([{"a": 1.0, "b": 1.0}, {"a": 0.5, "b": None}], cfg)
    assert out[0]["L"]["C3"] is None and "C3" not in out[0]["parts"]
    # Thesis quirk kept on purpose: with mid == hi, x >= hi gives mu 0 (not 1),
    # so a=1 -> 0 and the inverted b=1 -> 1.
    assert out[0]["L"]["C1"] == pytest.approx(0.5)
    assert out[0]["parts"]["C1"]["a"] == {"value": 1.0, "mu": 0.0, "w": 0.5}
    assert out[0]["parts"]["C1"]["b"]["mu"] == 1.0
    # a=0.5 -> 0.5; b missing -> mu 0 (missing values never count as evidence)
    assert out[1]["L"]["C1"] == pytest.approx(0.25)
    assert out[1]["parts"]["C1"]["b"]["value"] is None
