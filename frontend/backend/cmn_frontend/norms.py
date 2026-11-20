"""External reference ranges from published norms (D2), for the clinician view only.

There are no published norms for network-level metrics. norms.json holds verified norms for the
behaviours our metrics stand in for (sleep duration and timing, screen time, night-time phone use,
sleep regularity), each with its citation, population, table/page and a proxy note.

Most sources publish a mean and SD, not percentiles. The typical range P16-P84 (the central 68 %)
and a day's percentile are then computed **under a normal assumption** (marked as such in the
output); a source with one mean/SD row per year of age gives a mixture of normals over the rows of
the chosen age band, weighted by n. Sources with only a centre (a median, a mean, or the pooled
mean of a meta-analysis) give no range: they are returned as `points` for the tooltip, never used
for percentiles or flags.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
from statistics import NormalDist
from typing import Any

NORMS_PATH = Path(__file__).with_name("norms.json")
AGE_BANDS: dict[str, tuple[float, float]] = {"15-18": (15, 18), "19-24": (19, 24)}
DEFAULT_AGE_BAND = "15-18"
P_LOW, P_MID, P_HIGH = 16.0, 50.0, 84.0     # typical range = P16-P84 (±1 SD under a normal distribution)


def age_band() -> str:
    b = os.environ.get("CMN_NORM_AGE_BAND", DEFAULT_AGE_BAND)
    return b if b in AGE_BANDS else DEFAULT_AGE_BAND


@lru_cache(maxsize=4)
def load(path: str | None = None) -> dict[str, Any]:
    return json.loads(Path(path or NORMS_PATH).read_text(encoding="utf-8"))


def normal_percentile(x: float, mean: float, sd: float) -> float:
    """Percentile (0-100) of x in a normal distribution with this mean and SD."""
    if sd <= 0:
        return 50.0 if x == mean else (100.0 if x > mean else 0.0)
    return 100.0 * NormalDist(mean, sd).cdf(x)


def normal_quantile(p: float, mean: float, sd: float) -> float:
    """Value at percentile p (0-100) under a normal assumption."""
    return NormalDist(mean, max(sd, 1e-9)).inv_cdf(min(max(p / 100.0, 1e-6), 1 - 1e-6))


class Mixture:
    """A weighted mixture of normal distributions (one component per year of age, weighted by n)."""

    def __init__(self, components: list[tuple[float, float, float]]):
        tot = sum(w for w, _, _ in components)
        self.parts = [(w / tot, NormalDist(m, max(s, 1e-9))) for w, m, s in components]
        self.mean = sum(w * d.mean for w, d in self.parts)
        self.sd = math.sqrt(sum(w * (d.stdev ** 2 + d.mean ** 2) for w, d in self.parts) - self.mean ** 2)

    def percentile(self, x: float) -> float:
        return 100.0 * sum(w * d.cdf(x) for w, d in self.parts)

    def quantile(self, p: float) -> float:
        lo = min(d.mean - 8 * d.stdev for _, d in self.parts)
        hi = max(d.mean + 8 * d.stdev for _, d in self.parts)
        for _ in range(80):
            mid = (lo + hi) / 2
            if self.percentile(mid) < p:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2


def _overlaps(age: list[float] | None, band: tuple[float, float]) -> bool:
    return bool(age) and age[0] <= band[1] and age[1] >= band[0]


def entry_distribution(entry: dict[str, Any], band: tuple[float, float]) -> tuple[Mixture, int] | None:
    """(distribution, n) of an entry with a spread (mean_sd, mean_sd_by_age) in the age band."""
    if entry.get("stat") == "mean_sd":
        return Mixture([(1.0, entry["mean"], entry["sd"])]), int(entry.get("n") or 0)
    if entry.get("stat") == "mean_sd_by_age":
        rows = [r for r in entry["rows"] if band[0] <= r["age"] <= band[1]]
        if not rows:
            return None
        return Mixture([(r["n"], r["mean"], r["sd"]) for r in rows]), sum(r["n"] for r in rows)
    return None


def external_reference(band_key: str | None = None, norms: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The `external` reference for an age band: P16/P50/P84 per track, points and context.

    The result is the shape observed.build takes as `reference` (with `_pct`: track -> function
    value -> percentile, removed before it is sent).
    """
    band_key = band_key if band_key in AGE_BANDS else age_band()
    band = AGE_BANDS[band_key]
    norms = norms or load()
    sources = norms.get("sources", {})
    tracks: dict[str, dict[str, Any]] = {}
    stats: dict[str, dict[str, float]] = {}
    pct: dict[str, Any] = {}
    points: dict[str, list[dict[str, Any]]] = {}
    context: list[dict[str, Any]] = []
    for e in norms.get("entries", []):
        src = sources.get(e["source"], {})
        meta = {"citation": src.get("citation", e["source"]), "proxy_note": e.get("proxy_note", ""),
                "label": e.get("label", ""), "location": e.get("location", ""),
                "population": src.get("population", ""), "url": src.get("url", "")}
        if e.get("track") is None:
            context.append({**meta, "stat": e.get("stat"), "unit": e.get("unit"), "values": e.get("values"),
                            "iqr": e.get("iqr")})
            continue
        if not _overlaps(e.get("age"), band):
            continue
        track = e["track"]
        dist = entry_distribution(e, band)
        if dist is not None:
            if track in tracks:             # the first entry with a spread wins (order in norms.json)
                continue
            mix, n = dist
            tracks[track] = {"p16": round(mix.quantile(P_LOW), 3), "p50": round(mix.quantile(P_MID), 3),
                             "p84": round(mix.quantile(P_HIGH), 3), "n": n, **meta,
                             "normal_assumption": True, "day": e.get("day", "all"),
                             "age": e.get("age")}
            stats[track] = {"mean": mix.mean, "sd": mix.sd, "n": n}
            pct[track] = mix.percentile
        else:
            points.setdefault(track, []).append({**meta, "stat": e.get("stat"), "unit": e.get("unit"),
                                                 "values": e.get("values"), "ci95": e.get("ci95"),
                                                 "age": e.get("age"), "age_note": e.get("age_note")})
    if not tracks and not points:
        return None
    return {"source": "external", "label": f"typical {band_key.replace('-', '–')} y (published norms, proxies)",
            "age_band": band_key, "normal_assumption": True, "tracks": tracks, "points": points,
            "context": context, "stats": stats, "n_days": 0, "people": [], "_pct": pct}
