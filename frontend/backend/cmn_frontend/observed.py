"""Observed behaviour per day, the person's usual range, and risk flags (layer 1 of the portal).

Layer 1 shows what the network saw, in real units, before any model: when the devices went quiet at
night and came back, how long they were in use, night-time use, chat sessions, different sites, and
(clinicians and parents only) visits to crisis or self-harm sites. A *flag* names a risk over the
recent days, e.g. "Later nights: on 4 of the last 7 nights", not a single unusual day. A flag has a
*kind*: "risk" (in the direction the care plan watches) or "change" (a notable change in the improving
direction, shown neutrally as something to discuss), and an *icon* (names as in the frontend's Icon).

Besides the person's own usual range there is a *typical* range from a reference group: P16-P84 per
track, either empirical percentiles of other people's pooled usual days ("pooled") or published norms
for the behaviour a metric stands in for ("external", see norms.py; normal assumption, proxies only).

"In use" means at least ACTIVE_PACKETS packets in a 5-minute bin. Scripted devices are silent
between their blocks, so any cutoff works for them; real phones send background traffic (push,
sync, updates) all night, so the cutoff must be tuned on a real device (CMN_ACTIVE_PACKETS).
The quiet window is therefore called "quiet window", not "sleep": the network cannot tell asleep
from away or switched off.
"""

from __future__ import annotations

import math
import os
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import NormalDist
from typing import Any, Callable

from . import metric_names

BIN_MIN = 5
BINS_PER_DAY = 24 * 60 // BIN_MIN
NIGHT_FROM_HOUR = 18          # a night runs from 18:00 the day before ...
NIGHT_TO_HOUR = 14            # ... to 14:00 on the day it is counted for
MIN_QUIET_MIN = 60            # shorter gaps are not a quiet window
BRIEF_USE_MIN = 15            # a use this short (a phone check) between 00:00 and ...
BRIEF_UNTIL_HOUR = 5          # ... 05:00 does not end the quiet window
DEVIATION_Z = 1.5             # a day counts as different from usual beyond 1.5 SD
FLAG_DAYS = 3                 # a risk is flagged when at least 3 ...
FLAG_WINDOW = 7               # ... of the last 7 days with data deviate in its direction
SENSITIVE_WINDOW = 14         # sensitive sites: any signal in the last 14 days
MIN_REFERENCE_DAYS = 7        # a typical (reference-group) range needs at least 7 days of other people
IRREGULAR_WINDOW = 7          # irregular nights: SD of the went-quiet time over the last 7 nights ...
IRREGULAR_MIN_NIGHTS = 4      # ... with at least 4 of them known
P_LOW, P_MID, P_HIGH = 16.0, 50.0, 84.0   # typical range = P16-P84 (the central 68 %)
MIN_TYPE_DAYS = 5             # usual range per day type (away / home / free) from 5 baseline days of it
OUTSIDE_NORMAL = 3.0          # a value outside the clinician's normal range counts as clearly different


def active_packets() -> int:
    try:
        return max(1, int(os.environ.get("CMN_ACTIVE_PACKETS", "50")))
    except ValueError:
        return 50


@dataclass(frozen=True)
class Track:
    key: str
    label: str            # everyday wording, shown to everyone
    unit: str
    sd_floor: float       # smallest SD used for the deviation (avoids flags from tiny baselines)
    sensitive: bool = False
    icon: str = ""        # Icon name in the frontend


TRACKS: list[Track] = [
    Track("quiet_start", "Went quiet", "time", 30.0, icon="moon"),
    Track("quiet_end", "Back online", "time", 30.0, icon="sunrise"),
    Track("quiet_hours", "Quiet window", "h", 0.5, icon="moon"),
    Track("online_hours", "Time in use", "h", 0.5, icon="clock"),
    Track("night_minutes", "Use at night (00–06)", "min", 15.0, icon="night-use"),
    Track("chat_sessions", "Chat sessions", "count", 1.0, icon="chat"),
    Track("sites", "Different sites", "count", 5.0, icon="globe"),
    # SD of the went-quiet time over the last 7 nights (D5); compared with the baseline's rolling SD
    Track("quiet_start_sd7", "Irregular nights (spread of went quiet, 7 nights)", "min", 10.0, icon="irregular"),
    Track("sensitive_days", "Crisis or self-harm sites", "flag", 0.0, sensitive=True, icon="alert"),
]
TRACK_BY_KEY = {t.key: t for t in TRACKS}


@dataclass(frozen=True)
class Risk:
    id: str
    title: str
    track: str
    direction: int        # +1: higher than usual is the risk, -1: lower
    text: str             # "{n} of the last {w} nights"
    change_title: str = ""   # the improving direction (E1); empty when both directions are risks
    change_text: str = ""


RISKS: list[Risk] = [
    Risk("later_nights", "Later nights", "quiet_start", +1, "went quiet later than usual",
         "Earlier nights", "went quiet earlier than usual"),
    Risk("later_mornings", "Later mornings", "quiet_end", +1, "came back online later than usual",
         "Earlier mornings", "came back online earlier than usual"),
    Risk("shorter_quiet", "Shorter quiet window at night", "quiet_hours", -1, "had a shorter quiet window than usual",
         "Longer quiet window at night", "had a longer quiet window than usual"),
    Risk("night_use", "More use at night", "night_minutes", +1, "had more use between 00:00 and 06:00 than usual",
         "Less use at night", "had less use between 00:00 and 06:00 than usual"),
    Risk("more_use", "More time in use", "online_hours", +1, "devices were in use longer than usual"),
    Risk("less_use", "Less time in use", "online_hours", -1, "devices were in use less than usual"),
    Risk("fewer_chats", "Fewer chat sessions", "chat_sessions", -1, "had fewer chat sessions than usual",
         "More chat sessions", "had more chat sessions than usual"),
    Risk("fewer_sites", "Fewer different sites", "sites", -1, "used fewer different sites than usual",
         "More different sites", "used more different sites than usual"),
    Risk("irregular_nights", "Irregular nights", "quiet_start_sd7", +1,
         "went quiet at more irregular times than usual",
         "More regular nights", "went quiet at more regular times than usual"),
]
CHANGE_ICON = "change"

# Not a crisis/self-harm signal: without URLs in the gateway data this counts all reddit.com packets.
NOT_SENSITIVE = {"C9_F4_SelfHarmForumVisits"}


def _num(x: Any) -> float | None:
    if isinstance(x, bool) or x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _active(bins: list[int] | None, cutoff: int) -> list[bool] | None:
    if not bins or len(bins) != BINS_PER_DAY:
        return None
    return [b >= cutoff for b in bins]


def quiet_window(prev_active: list[bool] | None, active: list[bool] | None) -> dict[str, float] | None:
    """When the devices went quiet at night and came back (minutes from midnight; negative = evening).

    Between 18:00 the day before and 14:00: stretches without use, where short uses of up to
    BRIEF_USE_MIN between 00:00 and 05:00 (a phone check in the night) do not end the stretch; that
    use is counted in "Use at night".
    The quiet window is the longest such stretch that overlaps 00:00–06:00, so a silent day at work
    or school is not mistaken for the night. None when a needed day has no data, when there was no
    use at all (devices away or off), or when no stretch of at least MIN_QUIET_MIN overlaps the night.
    """
    if prev_active is None or active is None:
        return None
    start_bin = NIGHT_FROM_HOUR * 60 // BIN_MIN
    end_bin = NIGHT_TO_HOUR * 60 // BIN_MIN
    seq = prev_active[start_bin:] + active[:end_bin]
    if not any(seq):
        return None
    # runs of inactivity as [start, end) bin ranges
    runs, run_start = [], None
    for i, a in enumerate(seq + [True]):
        if not a and run_start is None:
            run_start = i
        elif a and run_start is not None:
            runs.append([run_start, i])
            run_start = None
    offset = (24 - NIGHT_FROM_HOUR) * 60 // BIN_MIN        # bin 0 of seq is 18:00 the day before
    night = (offset, offset + 6 * 60 // BIN_MIN)            # 00:00-06:00 in seq bins
    core = (offset, offset + BRIEF_UNTIL_HOUR * 60 // BIN_MIN)
    # merge runs separated by a short use in the core of the night (a phone check at 02:00); a use
    # in the evening or the morning (going to bed, waking up) still ends the quiet window
    brief = BRIEF_USE_MIN // BIN_MIN
    merged = []
    for r in runs:
        gap = (merged[-1][1], r[0]) if merged else None
        if gap and gap[1] - gap[0] <= brief and gap[0] >= core[0] and gap[1] <= core[1]:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    cands = [r for r in merged if r[0] < night[1] and r[1] > night[0] and (r[1] - r[0]) * BIN_MIN >= MIN_QUIET_MIN]
    if not cands:
        return None
    s0, s1 = max(cands, key=lambda r: r[1] - r[0])
    start = (s0 - offset) * BIN_MIN
    end = (s1 - offset) * BIN_MIN
    return {"quiet_start": float(start), "quiet_end": float(end), "quiet_hours": (end - start) / 60}


def _ddmm(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}."


def _sensitive_item(metric: str, label: str, value: float | None, visits: dict[str, Any]) -> dict[str, Any]:
    """One sensitive signal of a day, in visits where the traffic summary has them (not packets)."""
    item: dict[str, Any] = {"metric": metric, "label": label, "value": value}
    v = visits.get(metric_names.SITE_GROUP_OF.get(metric, ""))
    if v:
        item.update(visits=v["visits"], starts=v["starts"], minutes=v["minutes"])
    return item


def _visit_text(s: dict[str, Any]) -> str:
    """ "2 visits (23:40, 23:58), about 3 min" or, without visit data, the measured value."""
    if s.get("visits"):
        n = s["visits"]
        return (f"{s['label'].lower()} {n} visit{'s' if n != 1 else ''} ({', '.join(s['starts'])}), "
                f"about {s['minutes']} min")
    return s["label"].lower()


def sensitive_metrics(metrics: dict[str, Any], baseline: dict[str, dict[str, float]]) -> list[str]:
    """C9 metrics above the person's baseline (mean + 2 SD, or above zero when always 0 before)."""
    out = []
    for k, v in metrics.items():
        if not k.startswith("C9_") or k in NOT_SENSITIVE:
            continue
        x = _num(v)
        if x is None or x <= 0:
            continue
        s = baseline.get(k)
        if s is None or x > s["mean"] + 2 * s["sd"]:
            out.append(k)
    return out


def _stats(vals: list[float]) -> dict[str, float] | None:
    if len(vals) < 3:
        return None
    return {"mean": statistics.fmean(vals), "sd": statistics.stdev(vals), "n": len(vals)}


def reference_stats(values: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    """Mean, SD and n per track of the reference group's pooled days (at least MIN_REFERENCE_DAYS)."""
    out = {}
    for t in TRACKS:
        if t.sensitive:
            continue
        s = _stats(values.get(t.key, []))
        if s and s["n"] >= MIN_REFERENCE_DAYS:
            out[t.key] = s
    return out


def empirical_range(vals: list[float]) -> dict[str, float]:
    """P16, P50, P84 of the values (linear interpolation between order statistics) and n."""
    if len(vals) < 2:
        v = vals[0] if vals else 0.0
        return {"p16": v, "p50": v, "p84": v, "n": len(vals)}
    q = statistics.quantiles(vals, n=100, method="inclusive")
    return {"p16": q[int(P_LOW) - 1], "p50": q[int(P_MID) - 1], "p84": q[int(P_HIGH) - 1], "n": len(vals)}


def empirical_percentile(sorted_vals: list[float], x: float) -> float:
    """Share of reference values below x (ties count half), 0-100."""
    below = sum(1 for v in sorted_vals if v < x)
    equal = sum(1 for v in sorted_vals if v == x)
    return 100.0 * (below + 0.5 * equal) / len(sorted_vals)


def pooled_reference(values: dict[str, list[float]], n_days: int = 0,
                     people: list[str] | None = None) -> dict[str, Any] | None:
    """The `pooled` typical reference: empirical P16/P50/P84 of other people's usual days per track."""
    tracks: dict[str, dict[str, Any]] = {}
    pct: dict[str, Callable[[float], float]] = {}
    for t in TRACKS:
        vals = sorted(values.get(t.key, []))
        if t.sensitive or len(vals) < MIN_REFERENCE_DAYS:
            continue
        tracks[t.key] = {k: (round(v, 3) if k != "n" else v) for k, v in empirical_range(vals).items()}
        pct[t.key] = (lambda vs: lambda x: empirical_percentile(vs, x))(vals)
    if not tracks:
        return None
    people = list(people or [])
    return {"source": "pooled",
            "label": "typical (other people's usual weeks)" if people else "typical (reference group)",
            "normal_assumption": False, "tracks": tracks, "stats": reference_stats(values),
            "n_days": n_days, "people": people, "_pct": pct}


def _normal_reference(stats: dict[str, dict[str, float]], **extra: Any) -> dict[str, Any] | None:
    """A reference from mean/SD per track only (normal assumption)."""
    tracks, pct = {}, {}
    for k, s in stats.items():
        if k not in TRACK_BY_KEY or TRACK_BY_KEY[k].sensitive or s.get("sd") is None:
            continue
        nd = NormalDist(s["mean"], max(s["sd"], 1e-9))
        tracks[k] = {"p16": round(nd.inv_cdf(P_LOW / 100), 3), "p50": round(s["mean"], 3),
                     "p84": round(nd.inv_cdf(P_HIGH / 100), 3), "n": s.get("n")}
        pct[k] = (lambda d: lambda x: 100.0 * d.cdf(x))(nd)
    if not tracks:
        return None
    return {"source": "pooled", "label": "typical (reference group)", "normal_assumption": True,
            "tracks": tracks, "stats": stats, "n_days": 0, "people": [], **extra, "_pct": pct}


def prepare_reference(reference: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalise what build() gets: a ready reference (with `_pct`), pooled values, or mean/SD stats."""
    if not reference:
        return None
    if "_pct" in reference:
        return reference if reference.get("tracks") or reference.get("points") else None
    if reference.get("values") is not None:
        return pooled_reference(reference["values"], reference.get("n_days", 0), reference.get("people"))
    if reference.get("stats"):
        return _normal_reference(reference["stats"], n_days=reference.get("n_days", 0),
                                 people=list(reference.get("people") or []))
    return None


def percentile_z(p: float) -> float:
    """The z of a percentile under a standard normal (clipped to P0.1-P99.9)."""
    return NormalDist().inv_cdf(min(max(p / 100.0, 0.001), 0.999))


def track_values(days: list[dict[str, Any]], select: Callable[[dict[str, Any]], bool]) -> dict[str, list[float]]:
    """Values per track of the selected days (for pooling a reference)."""
    out: dict[str, list[float]] = {}
    for d in days:
        if not select(d) or not d.get("observed"):
            continue
        for t in TRACKS:
            v = d["observed"].get(t.key)
            if not t.sensitive and v is not None:
                out.setdefault(t.key, []).append(v)
    return out


SENSITIVITY = {"strict": (1.0, 2), "standard": (DEVIATION_Z, FLAG_DAYS), "relaxed": (2.0, 4)}


def risk_setting(focus: dict[str, Any] | None, risk_id: str) -> tuple[bool, float, int, str]:
    """(enabled, deviation in SD, days needed among the last 7, sensitivity) for a risk."""
    f = (focus or {}).get(risk_id) or {}
    sens = f.get("sensitivity", "standard")
    z, need = SENSITIVITY.get(sens, SENSITIVITY["standard"])
    return bool(f.get("enabled", True)), z, need, sens


REFERENCE_PHRASE = "than is typical for the reference group"


def _risk_flags(days: list[dict[str, Any]], dev_key: str, basis: str,
                focus: dict[str, Any] | None = None, changes: bool = False) -> list[dict[str, Any]]:
    """Risk flags (and, with `changes`, change flags in the improving direction) over the last days."""
    flags = []
    days = [d for d in days if d["observed"].get("day_type") != "away_period"]
    for r in RISKS:
        enabled, z_need, need, sens = risk_setting(focus, r.id)
        if not enabled:
            continue
        window = [d for d in days if d["observed"].get(r.track) is not None][-FLAG_WINDOW:]
        unit = "nights" if r.track.startswith("quiet") or r.track == "night_minutes" else "days"
        devs = [(d["date"], (d["observed"].get(dev_key) or {}).get(r.track)) for d in window]
        hit = [day for day, zz in devs if zz is not None and zz * r.direction >= z_need]
        if len(window) >= need and len(hit) >= need:
            phrase = r.text if basis == "own" else r.text.replace("than usual", REFERENCE_PHRASE)
            flags.append({"id": r.id if basis == "own" else f"ref_{r.id}", "basis": basis,
                          "kind": "risk", "icon": TRACK_BY_KEY[r.track].icon,
                          "title": r.title if basis == "own" else f"{r.title} than typical",
                          "track": r.track, "direction": r.direction,
                          "days": hit, "count": len(hit), "window": len(window), "unit": unit, "phrase": phrase,
                          "text": f"On {len(hit)} of the last {len(window)} {unit} the person {phrase}.",
                          "sensitive": False, "sensitivity": sens})
        if not (changes and r.change_title):
            continue
        better = [day for day, zz in devs if zz is not None and -zz * r.direction >= z_need]
        if len(window) >= need and len(better) >= need:
            flags.append({"id": f"change_{r.id}", "basis": basis, "kind": "change", "icon": CHANGE_ICON,
                          "title": r.change_title, "track": r.track, "direction": -r.direction,
                          "days": better, "count": len(better), "window": len(window), "unit": unit,
                          "phrase": r.change_text,
                          "text": f"On {len(better)} of the last {len(window)} {unit} the person {r.change_text}. "
                                  f"A notable change to discuss, not a risk.",
                          "sensitive": False, "sensitivity": sens})
    return flags


def _rolling_sd(days: list[dict[str, Any]]) -> None:
    """quiet_start_sd7: SD of the went-quiet time over the last IRREGULAR_WINDOW calendar nights.

    Only on a day with a went-quiet time of its own, from at least IRREGULAR_MIN_NIGHTS known nights;
    nights in an away period do not count.
    """
    known = {d["date"]: d["observed"]["quiet_start"] for d in days
             if d["observed"].get("quiet_start") is not None and d["observed"].get("day_type") != "away_period"}
    for d in days:
        o = d["observed"]
        if d["date"] not in known:
            o["quiet_start_sd7"] = None
            continue
        day = date.fromisoformat(d["date"])
        vals = [v for k in range(IRREGULAR_WINDOW)
                if (v := known.get((day - timedelta(days=k)).isoformat())) is not None]
        o["quiet_start_sd7"] = statistics.stdev(vals) if len(vals) >= IRREGULAR_MIN_NIGHTS else None


def build(days: list[dict[str, Any]], activity: list[dict[str, Any] | None],
          metric_baseline: dict[str, dict[str, float]], labels: Callable[[str], str] | None = None,
          reference: dict[str, Any] | None = None, day_types: dict[str, str | None] | None = None,
          focus: dict[str, Any] | None = None, normals: dict[str, dict[str, float | None]] | None = None,
          changes: bool = True) -> dict[str, Any]:
    """Observed tracks per day, usual range from the complete baseline days, and risk flags.

    `days` are the timeline days (date, phase, complete, metrics) in date order; `activity` the
    matching day records' 5-minute activity. Adds `observed` to each day and returns the summary.
    `reference` adds a second comparison, with a *typical* range of a reference group: a ready
    reference from pooled_reference() / norms.external_reference(), {"values": pooled per-track
    values of other people's usual days, "n_days", "people"} (empirical percentiles), or {"stats":
    mean/SD per track} (normal assumption). Every day gets `percentile_ref` (0-100 per track) and
    `deviation_ref` (the percentile as a z, never more than |value - P50| / the track's SD floor, so a
    tiny difference from a narrow reference is no clear difference), and flags over the last days
    with data (these work from the first week, without waiting for the person's own baseline).
    `changes` adds "change" flags for notable changes in the improving direction (own basis only).

    From the care plan: `day_types` (date -> "away" | "home" | "free" | "away_period") gives usual
    ranges per day type once there are MIN_TYPE_DAYS baseline days of a type, and leaves away periods
    out of the usual ranges and the flags; `focus` (risk -> enabled, sensitivity) chooses which risks
    are flagged and how sensitively; `normals` (track -> min, max) replaces the learned usual range
    with the clinician's: a day outside it counts as clearly different.
    """
    cutoff = active_packets()
    by_date = {d["date"]: i for i, d in enumerate(days)}
    actives = [_active((a or {}).get("total"), cutoff) for a in activity]

    for i, d in enumerate(days):
        act = actives[i]
        prev_i = by_date.get((date.fromisoformat(d["date"]) - timedelta(days=1)).isoformat())
        qw = quiet_window(actives[prev_i] if prev_i is not None else None, act)
        m = d["metrics"]
        obs: dict[str, Any] = {
            "quiet_start": qw["quiet_start"] if qw else None,
            "quiet_end": qw["quiet_end"] if qw else None,
            "quiet_hours": qw["quiet_hours"] if qw else None,
            "online_hours": sum(act) * BIN_MIN / 60 if act else None,
            "night_minutes": float(sum(act[: 6 * 60 // BIN_MIN]) * BIN_MIN) if act else None,
            "chat_sessions": _num(m.get("C2_F3_ChatSessionCount")),
            "sites": _num(m.get("C2_F1_UniqueSLD")),
            "active_hourly": [sum(act[h * 12:(h + 1) * 12]) * BIN_MIN for h in range(24)] if act else None,
            "has_data": bool(act) and (d.get("packets_kept") or 0) > 0,
        }
        sens = sensitive_metrics(m, metric_baseline)
        visits = (activity[i] or {}).get("site_visits") or {}
        obs["site_visits"] = visits          # per site group: visits, start times, minutes (clinicians)
        obs["sensitive"] = [_sensitive_item(k, labels(k) if labels else metric_names.plain(k), _num(m[k]), visits)
                            for k in sens]
        obs["sensitive_days"] = 1.0 if sens else 0.0
        d["observed"] = obs

    day_types = day_types or {}
    normals = {k: v for k, v in (normals or {}).items() if k in TRACK_BY_KEY and v}
    for d in days:
        d["observed"]["day_type"] = day_types.get(d["date"])
    _rolling_sd(days)
    base = [d for d in days if d["phase"] == "baseline" and d["complete"]
            and d["observed"]["day_type"] != "away_period"]
    usual: dict[str, dict[str, float]] = {}
    usual_by_type: dict[str, dict[str, dict[str, float]]] = {}
    for t in TRACKS:
        if t.sensitive:
            continue
        s = _stats([v for d in base if (v := d["observed"].get(t.key)) is not None])
        if s:
            usual[t.key] = s
        for typ in ("away", "home", "free"):
            st = _stats([v for d in base if d["observed"]["day_type"] == typ and (v := d["observed"].get(t.key)) is not None])
            if st and st["n"] >= MIN_TYPE_DAYS:
                usual_by_type.setdefault(typ, {})[t.key] = st

    def z(track: str, v: float | None, typ: str | None) -> float | None:
        if v is None:
            return None
        n = normals.get(track)
        if n:   # the clinician's normal range: inside is usual, outside is clearly different
            lo, hi = n.get("min"), n.get("max")
            scale = max((usual.get(track) or {}).get("sd", 0.0), TRACK_BY_KEY[track].sd_floor)
            if hi is not None and v > hi:
                return OUTSIDE_NORMAL + (v - hi) / scale
            if lo is not None and v < lo:
                return -(OUTSIDE_NORMAL + (lo - v) / scale)
            return 0.0
        s = (usual_by_type.get(typ or "") or {}).get(track) or usual.get(track)
        if s is None:
            return None
        return (v - s["mean"]) / max(s["sd"], TRACK_BY_KEY[track].sd_floor)

    for d in days:
        typ = d["observed"]["day_type"]
        d["observed"]["deviation"] = {
            t.key: (round(zz, 2) if (zz := z(t.key, d["observed"].get(t.key), typ)) is not None else None)
            for t in TRACKS if not t.sensitive
        }

    ref = prepare_reference(reference)
    ref_pct: dict[str, Callable[[float], float]] = (ref or {}).get("_pct") or {}

    def pref(track: str, v: float | None) -> float | None:
        f = ref_pct.get(track)
        return None if f is None or v is None else f(v)

    def zref(track: str, v: float | None, p: float | None) -> float | None:
        if p is None or v is None:
            return None
        z_p = percentile_z(p)
        floor = TRACK_BY_KEY[track].sd_floor
        cap = abs(v - ref["tracks"][track]["p50"]) / floor if floor > 0 else abs(z_p)
        return math.copysign(min(abs(z_p), cap), z_p)

    if ref_pct:
        for d in days:
            o = d["observed"]
            pcts = {t.key: pref(t.key, o.get(t.key)) for t in TRACKS if not t.sensitive}
            o["percentile_ref"] = {k: (round(p, 1) if p is not None else None) for k, p in pcts.items()}
            o["deviation_ref"] = {
                k: (round(zz, 2) if (zz := zref(k, o.get(k), p)) is not None else None) for k, p in pcts.items()
            }

    current = [d for d in days if d["phase"] == "current" and d["complete"]]
    flags = _risk_flags(current, "deviation", "own", focus, changes=changes)
    if ref_pct:
        recent = [d for d in days if d["complete"] and d["observed"]["has_data"]]
        flags += _risk_flags(recent, "deviation_ref", "reference", focus)
    recent = [d for d in current if d["observed"]["has_data"]
              and d["observed"]["day_type"] != "away_period"][-SENSITIVE_WINDOW:]
    sens_days = [d for d in recent if d["observed"]["sensitive"]]
    if sens_days and risk_setting(focus, "sensitive_sites")[0]:
        names = sorted({s["label"] for d in sens_days for s in d["observed"]["sensitive"]})
        detail = "; ".join(f"{_ddmm(d['date'])}: " + ", ".join(_visit_text(s) for s in d["observed"]["sensitive"])
                           for d in sens_days)
        flags.append({"id": "sensitive_sites", "basis": "own", "kind": "risk", "icon": "alert",
                      "title": "Crisis or self-harm sites", "track": "sensitive_days",
                      "direction": 1, "days": [d["date"] for d in sens_days], "count": len(sens_days),
                      "window": len(recent), "unit": "days", "phrase": "", "names": names,
                      "text": f"{', '.join(names)} on {len(sens_days)} of the last {len(recent)} days, more than "
                              f"usual for this person ({detail}).",
                      "sensitive": True})

    return {
        "tracks": [{"key": t.key, "label": t.label, "unit": t.unit, "sensitive": t.sensitive, "icon": t.icon,
                    "risk": sorted({r.direction for r in RISKS if r.track == t.key}) or ([1] if t.sensitive else [])}
                   for t in TRACKS],
        "usual": usual,
        "usual_by_type": usual_by_type,
        "normals": normals,
        "focus": {r: {"enabled": e, "sensitivity": sv} for r in [x.id for x in RISKS] + ["sensitive_sites"]
                  for e, _, _, sv in [risk_setting(focus, r)]},
        "reference": ({k: v for k, v in ref.items() if not k.startswith("_")} if ref else None),
        "flags": flags,
        "params": {"active_packets": cutoff, "deviation_z": DEVIATION_Z, "flag_days": FLAG_DAYS,
                   "flag_window": FLAG_WINDOW, "sensitive_window": SENSITIVE_WINDOW,
                   "night_from_hour": NIGHT_FROM_HOUR, "night_to_hour": NIGHT_TO_HOUR,
                   "irregular_window": IRREGULAR_WINDOW, "typical_range": [P_LOW, P_HIGH], "changes": changes},
    }


def for_person(observed: dict[str, Any], days: list[dict[str, Any]]) -> None:
    """Remove sensitive-site tracks and flags, and the comparison with the typical (reference) range.

    The person never sees crisis or self-harm sites. The comparison with a reference group is for
    clinicians and parents: told to the person it could frame them (expectation effect).
    """
    observed["tracks"] = [t for t in observed["tracks"] if not t["sensitive"]]
    observed["flags"] = [f for f in observed["flags"] if not f["sensitive"] and f.get("basis") != "reference"]
    observed["reference"] = None
    for d in days:
        if d.get("observed"):
            d["observed"].pop("sensitive", None)
            d["observed"].pop("site_visits", None)
            d["observed"].pop("sensitive_days", None)
            d["observed"].pop("deviation_ref", None)
            d["observed"].pop("percentile_ref", None)
