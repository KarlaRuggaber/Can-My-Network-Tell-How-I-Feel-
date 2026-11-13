"""Criterion likelihoods L_k, the N-of-M gate and the episode decision, as on the app's Early Signs page.

The functions are not copied: they are taken from the page's source with Python's parser (`ast`) and executed in
a small namespace, so the evaluation always uses the page's current logic (mf_tri, mf_exp_ramp, mf_clip01,
mf_value, fasl_score, gate_present). The page itself cannot be imported, because it runs Streamlit at import.

Page logic (01_Early_Signs_Overview.py):
- L_k(day) = fasl_score(values of the criterion's metrics that day, cfg[C_k]); memberships capped at `tau`
- present_k = L_k >= theta on at least N of the last M days
- episode = present criteria >= 5 and at least one core symptom present
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .daily import APP_DIR

PAGE = APP_DIR / "pages" / "01_Early_Signs_Overview.py"
FUNCTIONS = ("mf_tri", "mf_exp_ramp", "mf_clip01", "mf_value", "fasl_score", "gate_present")
CRIT_KEYS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]
EPISODE_MIN_PRESENT = 5   # the page's rule: >= 5 present and one core symptom


def load_page_functions(cfg: dict) -> dict:
    """The page's scoring functions, executed with `cfg_state` = cfg (fasl_score reads its tau from there)."""
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    missing = set(FUNCTIONS) - {n.name for n in defs}
    if missing:
        raise RuntimeError(f"{PAGE.name}: functions not found: {sorted(missing)}")
    module = ast.Module(body=defs, type_ignores=[])
    ns = {"np": np, "pd": pd, "math": math, "cfg_state": cfg, "Dict": dict, "Any": object, "List": list,
          "Tuple": tuple, "__builtins__": __builtins__}
    exec(compile(module, str(PAGE), "exec"), ns)
    return {name: ns[name] for name in FUNCTIONS}


def load_config(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def likelihoods(daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Per day and criterion: L_k (columns L_C1 … L_C9), as the page's DF_L."""
    fn = load_page_functions(cfg)
    out = {"Date": pd.to_datetime(daily["Date"])}
    for crit in CRIT_KEYS:
        spec = cfg.get(crit, {}) or {}
        out[f"L_{crit}"] = [fn["fasl_score"]({k: _num(row.get(k)) for k in spec}, spec)
                            for _, row in daily.iterrows()]
    return pd.DataFrame(out)


def gate(lk: pd.DataFrame, cfg: dict) -> dict:
    """present per criterion, total, core and episode, for the days in `lk` (the page uses the last M days)."""
    fn = load_page_functions(cfg)
    theta, need, window = float(cfg.get("theta", 0.6)), int(cfg.get("N", 6)), int(cfg.get("M", 14))
    present = {c: bool(fn["gate_present"](lk[f"L_{c}"], theta=theta, need_days=need, window=window))
               for c in CRIT_KEYS}
    days_over = {c: int((lk[f"L_{c}"].tail(window) >= theta).sum()) for c in CRIT_KEYS}
    core = list(cfg.get("core_symptoms", ["C2"]))
    total = sum(present.values())
    return {"present": present, "days_over_theta": days_over, "total_present": total,
            "core_present": any(present[c] for c in core), "core": core,
            "episode": any(present[c] for c in core) and total >= EPISODE_MIN_PRESENT,
            "theta": theta, "N": need, "M": window, "days": len(lk.tail(window))}


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v
