"""Observed behaviour per day, the person's usual range, and risk flags (layer 1 of the portal).

Layer 1 shows what the network saw, in real units, before any model: when the devices went quiet at
night and came back, how long they were in use, night-time use, chat sessions, different sites, and
(clinicians and parents only) visits to crisis or self-harm sites. A *flag* names a risk over the
recent days, e.g. "Later nights: on 4 of the last 7 nights", not a single unusual day.

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
from typing import Any, Callable

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


TRACKS: list[Track] = [
    Track("quiet_start", "Went quiet", "time", 30.0),
    Track("quiet_end", "Back online", "time", 30.0),
    Track("quiet_hours", "Quiet window", "h", 0.5),
    Track("online_hours", "Time in use", "h", 0.5),
    Track("night_minutes", "Use at night (00–06)", "min", 15.0),
    Track("chat_sessions", "Chat sessions", "count", 1.0),
    Track("sites", "Different sites", "count", 5.0),
    Track("sensitive_days", "Crisis or self-harm sites", "flag", 0.0, sensitive=True),
]
TRACK_BY_KEY = {t.key: t for t in TRACKS}


@dataclass(frozen=True)
class Risk:
    id: str
    title: str
    track: str
    direction: int        # +1: higher than usual is the risk, -1: lower
    text: str             # "{n} of the last {w} nights"


RISKS: list[Risk] = [
    Risk("later_nights", "Later nights", "quiet_start", +1, "went quiet later than usual"),
    Risk("later_mornings", "Later mornings", "quiet_end", +1, "came back online later than usual"),
    Risk("shorter_quiet", "Shorter quiet window at night", "quiet_hours", -1, "had a shorter quiet window than usual"),
    Risk("night_use", "More use at night", "night_minutes", +1, "had more use between 00:00 and 06:00 than usual"),
    Risk("more_use", "More time in use", "online_hours", +1, "devices were in use longer than usual"),
    Risk("less_use", "Less time in use", "online_hours", -1, "devices were in use less than usual"),
    Risk("fewer_chats", "Fewer chat sessions", "chat_sessions", -1, "had fewer chat sessions than usual"),
    Risk("fewer_sites", "Fewer different sites", "sites", -1, "used fewer different sites than usual"),
]

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


def build(days: list[dict[str, Any]], activity: list[dict[str, Any] | None],
          metric_baseline: dict[str, dict[str, float]], labels: Callable[[str], str] | None = None,
          ) -> dict[str, Any]:
    """Observed tracks per day, usual range from the complete baseline days, and risk flags.

    `days` are the timeline days (date, phase, complete, metrics) in date order; `activity` the
    matching day records' 5-minute activity. Adds `observed` to each day and returns the summary.
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
        obs["sensitive"] = [{"metric": k, "label": labels(k) if labels else k, "value": _num(m[k])} for k in sens]
        obs["sensitive_days"] = 1.0 if sens else 0.0
        d["observed"] = obs

    base = [d for d in days if d["phase"] == "baseline" and d["complete"]]
    usual = {}
    for t in TRACKS:
        if t.sensitive:
            continue
        s = _stats([v for d in base if (v := d["observed"].get(t.key)) is not None])
        if s:
            usual[t.key] = s

    def z(track: str, v: float | None) -> float | None:
        s = usual.get(track)
        if s is None or v is None:
            return None
        return (v - s["mean"]) / max(s["sd"], TRACK_BY_KEY[track].sd_floor)

    for d in days:
        d["observed"]["deviation"] = {
            t.key: (round(zz, 2) if (zz := z(t.key, d["observed"].get(t.key))) is not None else None)
            for t in TRACKS if not t.sensitive
        }

    current = [d for d in days if d["phase"] == "current" and d["complete"]]
    flags = []
    for r in RISKS:
        window = [d for d in current if d["observed"].get(r.track) is not None][-FLAG_WINDOW:]
        hit = [d["date"] for d in window if (zz := d["observed"]["deviation"].get(r.track)) is not None
               and zz * r.direction >= DEVIATION_Z]
        if len(window) >= FLAG_DAYS and len(hit) >= FLAG_DAYS:
            unit = "nights" if r.track.startswith("quiet") or r.track == "night_minutes" else "days"
            flags.append({"id": r.id, "title": r.title, "track": r.track, "direction": r.direction,
                          "days": hit, "count": len(hit), "window": len(window), "unit": unit, "phrase": r.text,
                          "text": f"On {len(hit)} of the last {len(window)} {unit} the person {r.text}.",
                          "sensitive": False})
    recent = [d for d in current if d["observed"]["has_data"]][-SENSITIVE_WINDOW:]
    sens_days = [d for d in recent if d["observed"]["sensitive"]]
    if sens_days:
        names = sorted({s["label"] for d in sens_days for s in d["observed"]["sensitive"]})
        flags.append({"id": "sensitive_sites", "title": "Crisis or self-harm sites", "track": "sensitive_days",
                      "direction": 1, "days": [d["date"] for d in sens_days], "count": len(sens_days),
                      "window": len(recent), "unit": "days", "phrase": "", "names": names,
                      "text": f"Visits above the person's usual level on {len(sens_days)} of the last "
                              f"{len(recent)} days ({', '.join(names)}).",
                      "sensitive": True})

    return {
        "tracks": [{"key": t.key, "label": t.label, "unit": t.unit, "sensitive": t.sensitive,
                    "risk": sorted({r.direction for r in RISKS if r.track == t.key}) or ([1] if t.sensitive else [])}
                   for t in TRACKS],
        "usual": usual,
        "flags": flags,
        "params": {"active_packets": cutoff, "deviation_z": DEVIATION_Z, "flag_days": FLAG_DAYS,
                   "flag_window": FLAG_WINDOW, "sensitive_window": SENSITIVE_WINDOW,
                   "night_from_hour": NIGHT_FROM_HOUR, "night_to_hour": NIGHT_TO_HOUR},
    }


def for_person(observed: dict[str, Any], days: list[dict[str, Any]]) -> None:
    """Remove sensitive-site tracks and flags (the person never sees them)."""
    observed["tracks"] = [t for t in observed["tracks"] if not t["sensitive"]]
    observed["flags"] = [f for f in observed["flags"] if not f["sensitive"]]
    for d in days:
        if "observed" in d:
            d["observed"].pop("sensitive", None)
            d["observed"].pop("sensitive_days", None)
