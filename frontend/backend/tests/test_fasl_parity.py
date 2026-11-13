"""The FASL port must behave exactly like the Streamlit page it was copied from.

The page cannot be imported (it runs Streamlit at import time), so the original functions are
extracted from its source with ast and executed in an isolated namespace.
"""

import ast
import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cmn_frontend import fasl
from cmn_frontend.settings import load_settings

PAGE = load_settings().app_dir / "pages" / "01_Early_Signs_Overview.py"
FUNCS = ["mf_tri", "mf_exp_ramp", "mf_clip01", "mf_value", "fasl_score", "gate_present"]


@pytest.fixture(scope="module")
def page():
    if not PAGE.is_file():
        pytest.skip(f"{PAGE} not found")
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCS]
    assert sorted(n.name for n in nodes) == sorted(FUNCS)
    ns = {"np": np, "math": math, "pd": pd, "Dict": dict, "Any": object, "cfg_state": {"tau": 1.0}}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(PAGE), "exec"), ns)
    return ns


XS = [None, float("nan"), float("inf"), -100, -1, 0, 0.1, 0.3, 0.5, 0.6, 1, 3, 12, 40, 80, 1000]
PARAMS = [(0, 0.5, 1), (20, 80, 80), (0, 40, 40), (1, 1, 1), (-50, -25, 0), (0.3, 0.4, 0.6),
          (float("-inf"), 2, 5), (1, 3, float("inf")), (5, 2, 1)]


@pytest.mark.parametrize("mf_type", ["tri", "exp_ramp", "other"])
@pytest.mark.parametrize("invert", [False, True])
def test_mf_value_matches_page(page, mf_type, invert):
    for x, (lo, mid, hi), cap in itertools.product(XS, PARAMS, [None, 1.0, 0.5]):
        want = page["mf_value"](x, lo, mid, hi, invert, mf_type, cap)
        got = fasl.mf_value(x, lo, mid, hi, invert, mf_type, cap)
        assert got == pytest.approx(want, abs=1e-12, nan_ok=True), (x, lo, mid, hi, cap)


@pytest.mark.parametrize("tau", [1.0, 0.4])
def test_score_matches_page_on_live_config(page, tau):
    cfg = fasl.load_config(load_settings().fasl_config)
    page["cfg_state"]["tau"] = tau
    rng = np.random.default_rng(0)
    for crit, spec in cfg.criteria.items():
        if not spec:
            continue
        for _ in range(200):
            row = {}
            for k, m in spec.items():
                lo, hi = float(m["mf"]["lo"]), float(m["mf"]["hi"])
                span = (hi - lo) or 1.0
                row[k] = None if rng.random() < 0.05 else float(rng.uniform(lo - span, hi + span))
            want = page["fasl_score"](row, spec)
            got, _ = fasl.score_criterion(row, spec, tau)
            assert got == pytest.approx(want, abs=1e-12), (crit, row)


def test_rolling_gate_last_day_matches_page(page):
    rng = np.random.default_rng(1)
    for _ in range(300):
        n = int(rng.integers(1, 30))
        L = [None if rng.random() < 0.1 else float(rng.random()) for _ in range(n)]
        theta, need, window = float(rng.random()), int(rng.integers(1, 10)), int(rng.integers(1, 20))
        want = page["gate_present"](pd.Series(L, dtype=float), theta, need, window)
        got = fasl.gate_present_rolling(L, theta, need, window)[-1]
        assert got == want
        # and every prefix: the rolling gate is the page's gate evaluated on each day
        for i in range(n):
            assert fasl.gate_present_rolling(L, theta, need, window)[i] == page["gate_present"](
                pd.Series(L[: i + 1], dtype=float), theta, need, window)
