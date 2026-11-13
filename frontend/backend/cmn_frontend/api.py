"""HTTP API for the React UI. Reads the per-day cache only; it never computes metrics itself.

    uvicorn cmn_frontend.api:app --host 127.0.0.1 --port 8600
"""

from __future__ import annotations

import math
import statistics
from datetime import date
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from . import fasl
from .groundtruth import blocks_on_day, day_summary, load_plan, phase_by_day
from .personas import PHASE_LABEL, persona_meta
from .settings import Settings, load_settings
from .store import DayStore


@lru_cache(maxsize=1)
def _metric_labels(app_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    """dist_col -> label / criterion, from the thesis app's criterion definitions."""
    try:
        from .daily import load_metric_code
        code = load_metric_code(app_dir)  # type: ignore[arg-type]
        return code.labels, code.criterion_of
    except Exception:
        return {}, {}


def _phase(day: date, phases: dict[str, str]) -> str:
    p = phases.get(day.isoformat())
    if p:
        return PHASE_LABEL.get(p, p)
    if phases and day.isoformat() < min(phases):
        return "pre-run"
    return "post-run" if phases else "unknown"


def _baseline_stats(days: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Mean and SD of every metric over the complete baseline days (for trend bands)."""
    base = [d for d in days if d["phase"] == "baseline" and d["complete"]]
    keys = {k for d in base for k in d["metrics"]}
    out = {}
    for k in sorted(keys):
        vals = [d["metrics"][k] for d in base if isinstance(d["metrics"].get(k), (int, float))
                and not isinstance(d["metrics"].get(k), bool) and math.isfinite(d["metrics"][k])]
        if len(vals) >= 2:
            out[k] = {"mean": statistics.fmean(vals), "sd": statistics.stdev(vals), "n": len(vals)}
    return out


def build_timeline(dataset: str, settings: Settings, cfg: fasl.FaslConfig) -> dict[str, Any]:
    store = DayStore(settings.cache_dir)
    records = list(store.days(dataset))
    if not records:
        raise KeyError(dataset)
    blocks = load_plan(settings.run_dir, dataset)
    phases = phase_by_day(blocks)
    scores = fasl.score_days([r["metrics"] for _, r in records], cfg)

    days = []
    for i, ((day, rec), sc) in enumerate(zip(records, scores)):
        days.append({
            "date": day.isoformat(),
            "weekday": day.strftime("%a"),
            "phase": _phase(day, phases),
            "complete": i + 1 < len(records),   # a later day has data: the ingest moved on
            "n_partitions": rec.get("n_partitions"),
            "packets_kept": rec.get("packets_kept"),
            "first_packet": rec.get("first_packet"),
            "last_packet": rec.get("last_packet"),
            "computed_at": rec.get("computed_at"),
            "ground_truth": day_summary(blocks_on_day(blocks, day)),
            "metrics": {k: v for k, v in rec["metrics"].items() if k != "Date"},
            "L": sc["L"],
            "parts": sc["parts"],
        })

    gate = cfg.gate
    present = {c: fasl.gate_present_rolling([d["L"][c] for d in days], gate.theta, gate.need_days,
                                            gate.window)
               for c in fasl.CRIT_KEYS if cfg.configured(c)}
    episode = fasl.episode_flags(present, gate)
    meta = persona_meta(dataset)
    return {
        "dataset": dataset,
        "persona": meta,
        "days": days,
        "gate": {"params": {"theta": gate.theta, "N": gate.need_days, "M": gate.window,
                            "core": list(gate.core), "min_present": gate.min_present},
                 "present": present, "episode": episode},
        "baseline_stats": _baseline_stats(days),
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="Can My Network Tell How I Feel? – results API")
    app.add_middleware(GZipMiddleware, minimum_size=2048)

    def config() -> fasl.FaslConfig:
        return fasl.load_config(settings.fasl_config)  # re-read: edits apply without restart

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "cache_dir": str(settings.cache_dir),
                "datasets": DayStore(settings.cache_dir).datasets()}

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        labels, crit_of = _metric_labels(str(settings.app_dir))
        cfg = config()
        return {**cfg.to_json(), "criterion_names": fasl.CRIT_NAMES,
                "metric_labels": labels, "metric_criterion": crit_of,
                "fasl_config_path": str(settings.fasl_config)}

    @app.get("/api/personas")
    def personas() -> list[dict[str, Any]]:
        store = DayStore(settings.cache_dir)
        out = []
        for ds in store.datasets():
            days = [d for d, _ in store.days(ds)]
            meta = persona_meta(ds)
            out.append({"dataset": ds, "name": meta["name"], "condition": meta["condition"],
                        "first_day": days[0].isoformat(), "last_day": days[-1].isoformat(),
                        "n_days": len(days)})
        return out

    @app.get("/api/personas/{dataset}")
    def timeline(dataset: str) -> dict[str, Any]:
        try:
            return build_timeline(dataset, settings, config())
        except KeyError:
            raise HTTPException(404, f"no cached days for {dataset}; run the export first")

    @app.get("/api/personas/{dataset}/days/{day}")
    def day_detail(dataset: str, day: str) -> dict[str, Any]:
        try:
            d = date.fromisoformat(day)
        except ValueError:
            raise HTTPException(400, "day must be YYYY-MM-DD")
        rec = DayStore(settings.cache_dir).load(dataset, d)
        if rec is None:
            raise HTTPException(404, f"no cached result for {dataset} {day}")
        blocks = blocks_on_day(load_plan(settings.run_dir, dataset), d)
        return {"dataset": dataset, "date": day, "activity": rec.get("activity"),
                "blocks": [b.to_json() for b in blocks],
                "packets_raw": rec.get("packets_raw"), "packets_kept": rec.get("packets_kept"),
                "n_partitions": rec.get("n_partitions"),
                "last_partition_start": rec.get("last_partition_start")}

    if settings.web_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
    return app


app = create_app()
