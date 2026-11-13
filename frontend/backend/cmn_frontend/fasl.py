"""FASL scoring and DSM gate, ported from app/pages/01_Early_Signs_Overview.py.

The Streamlit page defines these functions at module level next to Streamlit calls, so they
cannot be imported. They are copied here without behavioural changes; tests/test_fasl_parity.py
extracts the original functions from the page source and checks that both give the same results.

Differences to the page, both deliberate:
- tau is passed in explicitly instead of being read from Streamlit's session state.
- The gate is evaluated for every day (rolling), not only for the last M days, so the UI can show
  when a criterion turns present. For the last day it is identical to the page's gate_present().
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

CRIT_KEYS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]

CRIT_NAMES = {
    "C1": "Depressed mood",
    "C2": "Loss of interest / anhedonia",
    "C3": "Appetite / weight change",
    "C4": "Sleep timing & duration",
    "C5": "Psychomotor agitation / retardation",
    "C6": "Fatigue / low energy",
    "C7": "Worthlessness / guilt",
    "C8": "Difficulty concentrating / indecisiveness",
    "C9": "Suicidality",
}


# ------------------------------ membership functions ------------------------------

def mf_tri(x: float | None, lo: float, mid: float, hi: float, invert: bool = False) -> float:
    if x is None or (isinstance(x, float) and (np.isnan(x) or not np.isfinite(x))):
        return 0.0
    try:
        x_val, lo_val, mid_val, hi_val = float(x), float(lo), float(mid), float(hi)
    except Exception:
        return 0.0

    in_band = True
    if np.isfinite(lo_val) and x_val < lo_val:
        in_band = False
    if np.isfinite(hi_val) and x_val > hi_val:
        in_band = False

    if lo_val == mid_val == hi_val:
        val = 1.0
    elif not np.isfinite(lo_val) and not np.isfinite(hi_val):
        val = 1.0
    elif not np.isfinite(lo_val):
        if x_val <= mid_val:
            val = 1.0
        elif x_val >= hi_val:
            val = 0.0
        else:
            val = (hi_val - x_val) / max(1e-9, (hi_val - mid_val))
    elif not np.isfinite(hi_val):
        if x_val >= mid_val:
            val = 1.0
        elif x_val <= lo_val:
            val = 0.0
        else:
            val = (x_val - lo_val) / max(1e-9, (mid_val - lo_val))
    else:
        if x_val <= lo_val or x_val >= hi_val:
            val = 0.0
        elif x_val == mid_val:
            val = 1.0
        elif x_val < mid_val:
            val = (x_val - lo_val) / max(1e-9, (mid_val - lo_val))
        else:
            val = (hi_val - x_val) / max(1e-9, (hi_val - mid_val))

    val = float(np.clip(val, 0.0, 1.0))
    if invert:
        val = 1.0 - val
    if not in_band:
        return 0.0
    return float(np.clip(val, 0.0, 1.0))


def mf_exp_ramp(x: float | None, lo: float, x0: float, hi: float, invert: bool = False) -> float:
    if x is None or (isinstance(x, float) and (np.isnan(x) or not np.isfinite(x))):
        return 0.0
    try:
        x_val, lo_val, x0_val, hi_val = float(x), float(lo), float(x0), float(hi)
    except Exception:
        return 0.0

    if not np.isfinite(lo_val):
        lo_val = float(x0_val if np.isfinite(x0_val) else x_val)
    if not np.isfinite(hi_val):
        hi_val = float(x0_val if np.isfinite(x0_val) else x_val)
    if not np.isfinite(x0_val):
        finite_bounds = [v for v in (lo_val, hi_val) if np.isfinite(v)]
        x0_val = sum(finite_bounds) / len(finite_bounds) if finite_bounds else 0.0

    lo_val, x0_val, hi_val = sorted((lo_val, x0_val, hi_val))
    in_band = True
    if np.isfinite(lo_val) and x_val < lo_val:
        in_band = False
    if np.isfinite(hi_val) and x_val > hi_val:
        in_band = False
    if math.isclose(hi_val, lo_val, rel_tol=1e-9, abs_tol=1e-9):
        val = 1.0 if x_val >= hi_val else 0.0
        if invert:
            val = 1.0 - val
        if not in_band:
            return 0.0
        return float(np.clip(val, 0.0, 1.0))

    if x_val <= lo_val:
        val = 0.0
    elif x_val >= hi_val:
        val = 1.0
    else:
        span_left = max(1e-9, x0_val - lo_val)
        slope = math.log(2.0) / span_left
        full_span = max(1e-9, hi_val - lo_val)
        denom = 1.0 - math.exp(-slope * full_span)
        numerator = 1.0 - math.exp(-slope * (x_val - lo_val))
        val = float(np.clip(numerator / max(1e-9, denom), 0.0, 1.0))
    if invert:
        val = 1.0 - val
    if not in_band:
        return 0.0
    return float(np.clip(val, 0.0, 1.0))


def mf_clip01(x: float | None) -> float:
    try:
        return float(np.clip(float(x), 0.0, 1.0))
    except Exception:
        return 0.0


def mf_value(x, lo, mid, hi, invert: bool, mf_type: str, cap: float | None = None) -> float:
    mft = str(mf_type or "tri").lower()
    if mft in {"tri", "triangle", "triangular"}:
        val = mf_tri(x, lo, mid, hi, invert=invert)
    elif mft in {"exp_ramp", "exp", "one_sided_exponential_ramp", "one_sided_exp_ramp"}:
        val = mf_exp_ramp(x, lo, mid, hi, invert=invert)
    else:
        base = mf_clip01(x)
        val = float(1.0 - base if invert else base)
    val = float(np.clip(val, 0.0, 1.0))
    if cap is not None and np.isfinite(cap):
        val = float(min(val, float(np.clip(cap, 0.0, 1.0))))
    return val


# ------------------------------------ scoring ------------------------------------

@dataclass
class MetricScore:
    value: float | None
    mu: float
    w: float

    @property
    def contribution(self) -> float:
        return self.w * self.mu


def score_criterion(values: Mapping[str, Any], spec: Mapping[str, Any], tau: float = 1.0
                    ) -> tuple[float, dict[str, MetricScore]]:
    """Likelihood L_k of one criterion for one day, plus the per-metric breakdown.

    Same as the page's fasl_score(): sum of w * mu, clipped to [0, 1] (weights are not normalised).
    """
    cap = float(np.clip(float(tau), 0.0, 1.0)) if tau is not None else None
    total = 0.0
    parts: dict[str, MetricScore] = {}
    for key, cfg in (spec or {}).items():
        w = float(cfg.get("w", 0.0))
        mf_cfg = cfg.get("mf", {})
        x = values.get(key)
        mu = mf_value(
            x,
            float(mf_cfg.get("lo", 0.0)), float(mf_cfg.get("mid", 0.0)), float(mf_cfg.get("hi", 0.0)),
            invert=bool(mf_cfg.get("invert", False)),
            mf_type=(mf_cfg.get("type") or "tri").lower(),
            cap=cap,
        )
        total += w * mu
        parts[key] = MetricScore(value=_finite_or_none(x), mu=mu, w=w)
    return float(np.clip(total, 0.0, 1.0)), parts


def _finite_or_none(x: Any) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# -------------------------------------- gate --------------------------------------

@dataclass(frozen=True)
class GateParams:
    theta: float
    need_days: int   # N
    window: int      # M
    core: tuple[str, ...]
    min_present: int = 5


def gate_present_rolling(likelihoods: Sequence[float | None], theta: float, need_days: int,
                         window: int) -> list[bool]:
    """present[i] = at least `need_days` of the last `window` days up to day i have L >= theta.

    "Days" are rows with data, as in the page (tail(window) after dropna). A missing L
    (None/NaN) is skipped, not counted as a day.
    """
    out: list[bool] = []
    hist: list[float] = []
    for v in likelihoods:
        f = _finite_or_none(v)
        if f is not None:
            hist.append(f)
        tail = hist[-int(window):] if window > 0 else []
        out.append(bool(tail) and sum(1 for x in tail if x >= float(theta)) >= int(need_days))
    return out


def episode_flags(present: Mapping[str, Sequence[bool]], params: GateParams) -> list[bool]:
    """Episode likely on day i: >= min_present criteria present and at least one core criterion."""
    n = max((len(v) for v in present.values()), default=0)
    out = []
    for i in range(n):
        on = [c for c, v in present.items() if i < len(v) and v[i]]
        out.append(len(on) >= params.min_present and any(c in on for c in params.core))
    return out


# ------------------------------------- config -------------------------------------

@dataclass
class FaslConfig:
    M: int
    N: int
    theta: float
    tau: float
    core: list[str]
    criteria: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def gate(self) -> GateParams:
        return GateParams(theta=self.theta, need_days=self.N, window=self.M, core=tuple(self.core))

    def configured(self, crit: str) -> bool:
        return bool(self.criteria.get(crit))

    def to_json(self) -> dict[str, Any]:
        return {"M": self.M, "N": self.N, "theta": self.theta, "tau": self.tau,
                "core": self.core, "criteria": self.criteria}


def load_config(path: Path) -> FaslConfig:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    core = raw.get("core_symptoms", raw.get("core", ["C2"]))
    if isinstance(core, str):
        core = [core]
    return FaslConfig(
        M=int(raw.get("M", 14)),
        N=int(raw.get("N", 10)),
        theta=float(raw.get("theta", 0.7)),
        tau=float(raw.get("tau", 1.0)),
        core=[str(c) for c in core],
        criteria={c: dict(raw.get(c) or {}) for c in CRIT_KEYS},
    )


def score_days(rows: Iterable[Mapping[str, Any]], cfg: FaslConfig) -> list[dict[str, Any]]:
    """Likelihoods and per-metric breakdown for each daily metric row (in the given order)."""
    out = []
    for row in rows:
        day: dict[str, Any] = {"L": {}, "parts": {}}
        for crit in CRIT_KEYS:
            spec = cfg.criteria.get(crit) or {}
            if not spec:
                day["L"][crit] = None   # not configured: no likelihood (the page shows 0)
                continue
            L, parts = score_criterion(row, spec, cfg.tau)
            day["L"][crit] = L
            day["parts"][crit] = {k: {"value": p.value, "mu": p.mu, "w": p.w} for k, p in parts.items()}
        out.append(day)
    return out
