"""Baseline phase vs. clinical phase per persona, against the expectations in `expectations.yaml`.

For every metric: median in each phase and Cliff's delta d = P(profile > baseline) - P(profile < baseline), a rank
effect size that needs no distribution assumption and works with few days. |d| >= 0.33 counts as a change
(medium effect, Romano et al. 2006); below that "no change". The observed direction is compared with the
profile's expected one. With the thesis config the page's scoring (L_k, gate, episode) is applied per phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from . import scoring

D_CHANGE = 0.33
EXPECTATIONS = Path(__file__).resolve().parent.parent / "expectations.yaml"


def cliffs_delta(after: np.ndarray, before: np.ndarray) -> float | None:
    a, b = np.asarray(after, float), np.asarray(before, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return None
    greater = (a[:, None] > b[None, :]).sum()
    less = (a[:, None] < b[None, :]).sum()
    return float((greater - less) / (len(a) * len(b)))


def direction(d: float | None) -> str:
    if d is None:
        return "n/a"
    return "up" if d >= D_CHANGE else "down" if d <= -D_CHANGE else "no change"


@dataclass
class MetricRow:
    metric: str
    expected: str           # up / down / unchanged / ""
    n_base: int
    n_prof: int
    median_base: float | None
    median_prof: float | None
    d: float | None
    observed: str
    verdict: str            # as expected / opposite / no change / changed (expected none) / unchanged (ok) / n/a


def compare_metrics(daily: pd.DataFrame, exp: dict, all_metrics: bool = False) -> list[MetricRow]:
    base = daily[daily["phase"] == "baseline"]
    prof = daily[daily["phase"] == "profile"]
    wanted = {m: d for m, d in (exp.get("metrics") or {}).items()}
    wanted.update({m: "unchanged" for m in exp.get("unchanged") or []})
    if all_metrics:
        for c in daily.columns:
            if c not in wanted and pd.api.types.is_numeric_dtype(daily[c]) and c not in ("seed",):
                wanted[c] = ""
    rows = []
    for m, want in wanted.items():
        if m not in daily.columns:
            rows.append(MetricRow(m, want, 0, 0, None, None, None, "n/a", "metric missing"))
            continue
        b, p = pd.to_numeric(base[m], errors="coerce"), pd.to_numeric(prof[m], errors="coerce")
        d = cliffs_delta(p.values, b.values)
        obs = direction(d)
        if obs == "n/a":
            verdict = "n/a"
        elif want == "unchanged":
            verdict = "unchanged (ok)" if obs == "no change" else f"changed {obs} (expected none)"
        elif want in ("up", "down"):
            verdict = "as expected" if obs == want else "no change" if obs == "no change" else "opposite"
        else:
            verdict = "" if obs == "no change" else f"changed {obs}"
        rows.append(MetricRow(m, want, int(b.notna().sum()), int(p.notna().sum()),
                              _med(b), _med(p), d, obs, verdict))
    return rows


def score_phases(daily: pd.DataFrame, cfg: dict) -> dict:
    """The page's gate per phase (each phase scored on its own days, as the page scores the last M days)."""
    out = {}
    for phase in ("baseline", "profile"):
        days = daily[daily["phase"] == phase].sort_values("Date")
        if days.empty:
            continue
        lk = scoring.likelihoods(days, cfg)
        out[phase] = {"likelihoods": lk, **scoring.gate(lk, cfg)}
    return out


def _med(s: pd.Series) -> float | None:
    s = s.dropna()
    return float(s.median()) if len(s) else None


def load_expectations(path: Path = EXPECTATIONS) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def fmt(x: float | None) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "–"
    ax = abs(x)
    return f"{x:,.0f}" if ax >= 1000 else f"{x:.1f}" if ax >= 10 else f"{x:.3g}"


def report(eval_dir: Path, cfg_path: Path, out: Path, all_metrics: bool = False) -> Path:
    expectations = load_expectations()
    cfg = scoring.load_config(cfg_path)
    lines = ["# Live run 25.10–22.11: baseline vs. clinical phase", "",
             f"Daily metrics from `{eval_dir}` (app's metric code, one day at a time). Config for L_k/gate: "
             f"`{cfg_path.name}` (θ = {cfg.get('theta')}, N = {cfg.get('N')} of M = {cfg.get('M')}, "
             f"core = {cfg.get('core_symptoms')}). Change = |Cliff's d| ≥ {D_CHANGE}.", ""]
    metric_rows = []
    for ds, exp in expectations.items():
        path = eval_dir / f"{ds}.daily.csv"
        if not path.exists():
            lines += [f"## {ds}", "", f"no daily table ({path.name})", ""]
            continue
        daily = pd.read_csv(path, parse_dates=["Date"])
        n_b = int((daily["phase"] == "baseline").sum())
        n_p = int((daily["phase"] == "profile").sum())
        lines += [f"## {ds}: {exp['baseline']} → {exp['profile']}", "",
                  f"Baseline days: {n_b}, clinical days: {n_p}.", ""]
        rows = compare_metrics(daily, exp, all_metrics)
        lines += ["| Metric | Expected | Baseline median | Clinical median | Cliff's d | Observed | Verdict |",
                  "|---|---|---|---|---|---|---|"]
        for r in rows:
            if not all_metrics or r.expected or r.verdict:
                lines.append(f"| `{r.metric}` | {r.expected or '–'} | {fmt(r.median_base)} | {fmt(r.median_prof)} | "
                             f"{fmt(r.d)} | {r.observed} | {r.verdict} |")
            metric_rows.append({"dataset": ds, **r.__dict__})
        lines.append("")
        scores = score_phases(daily, cfg)
        lines += ["| Criterion | Expected (profile) | Days L ≥ θ, baseline | Days L ≥ θ, clinical | Present, clinical |",
                  "|---|---|---|---|---|"]
        for c in scoring.CRIT_KEYS:
            want = (exp.get("criteria") or {}).get(c, "absent")
            b = scores.get("baseline", {}).get("days_over_theta", {}).get(c, "–")
            p = scores.get("profile", {}).get("days_over_theta", {}).get(c, "–")
            pres = scores.get("profile", {}).get("present", {}).get(c)
            lines.append(f"| {c} | {want} | {b} | {p} | {'yes' if pres else 'no' if pres is not None else '–'} |")
        prof = scores.get("profile", {})
        lines += ["", f"Episode (clinical phase, {prof.get('days', 0)} days): "
                      f"**{'yes' if prof.get('episode') else 'no'}** "
                      f"({prof.get('total_present', 0)} present, core present: {prof.get('core_present')}); "
                      f"expected: {exp.get('episode')}.", ""]
        if prof.get("days", 0) < cfg.get("M", 14):
            lines += [f"Note: the clinical phase has {prof.get('days', 0)} of {cfg.get('M', 14)} days so far; "
                      f"a criterion needs L ≥ θ on {cfg.get('N', 6)} of them.", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(metric_rows).to_csv(out.with_suffix(".metrics.csv"), index=False)
    return out
