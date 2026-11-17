"""Onboarding and care plan per person: the patient's routine and devices, away periods, and the
clinician's setup (history, focus, sensitivity, own normal ranges).

- *Routine* (written by the patient in onboarding, changeable later; also by clinicians/parents):
  per weekday whether the day is spent away (work, school), at home (home office, remote school) or
  free; usual times away, bedtime and waking; the devices in plain words ("iPhone", "school
  laptop"). Clinicians or parents link each named device to an address seen on the network.
- *Away periods* (patient or clinician): holidays, hospital stays, travel. These days are left out of
  the usual ranges and the flags, since the home network cannot see them.
- *Clinical setup* (clinicians and parents): history, current concerns, treatment; which risks are
  tracked and how sensitively; normal ranges that replace the learned ones for this person.

Stored in <home>/care.json (owner-only). Never shown to the person: the clinical setup.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_TYPES = ("away", "home", "free")
DEVICE_KINDS = ("phone", "laptop", "tablet", "computer", "console", "tv", "other")
SENSITIVITY = {                       # deviation (SD) and days needed among the last 7
    "strict": {"z": 1.0, "days": 2},
    "standard": {"z": 1.5, "days": 3},
    "relaxed": {"z": 2.0, "days": 4},
}
MAX_TEXT = 4000
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def minutes(hhmm: str | None) -> int | None:
    if not hhmm or not _TIME.match(hhmm):
        return None
    return int(hhmm[:2]) * 60 + int(hhmm[3:])


def _text(v: Any, field: str, limit: int = MAX_TEXT) -> str:
    s = str(v or "").strip()
    if len(s) > limit:
        raise ValueError(f"{field}: at most {limit} characters")
    return s


def clean_routine(r: dict[str, Any]) -> dict[str, Any]:
    week = r.get("week") or {}
    out_week = {}
    for d in WEEKDAYS:
        t = week.get(d, "free" if d in ("sat", "sun") else "away")
        if t not in DAY_TYPES:
            raise ValueError(f"{d}: day type must be one of {', '.join(DAY_TYPES)}")
        out_week[d] = t
    times = {}
    for k in ("away_from", "away_to", "bedtime", "wake", "bedtime_free", "wake_free"):
        v = r.get(k) or None
        if v is not None and not _TIME.match(str(v)):
            raise ValueError(f"{k}: time as HH:MM")
        times[k] = v
    devices = []
    for d in r.get("devices") or []:
        name = _text(d.get("name"), "device name", 60)
        if not name:
            continue
        kind = d.get("kind") or "other"
        if kind not in DEVICE_KINDS:
            raise ValueError(f"device kind must be one of {', '.join(DEVICE_KINDS)}")
        ip = (d.get("ip") or "").strip() or None
        if ip and not re.match(r"^[0-9a-fA-F:.]+$", ip):
            raise ValueError(f"not an IP address: {ip!r}")
        devices.append({"id": d.get("id") or secrets.token_hex(4), "name": name, "kind": kind,
                        "shared": bool(d.get("shared")), "ip": ip})
    if len(devices) > 20:
        raise ValueError("at most 20 devices")
    return {"week": out_week, **times, "devices": devices, "note": _text(r.get("note"), "note", 1000)}


def clean_away(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in periods or []:
        try:
            f, t = date.fromisoformat(p["from"]), date.fromisoformat(p["to"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("away periods need a from and a to date (YYYY-MM-DD)")
        if t < f:
            raise ValueError("away period ends before it starts")
        out.append({"id": p.get("id") or secrets.token_hex(4), "from": f.isoformat(), "to": t.isoformat(),
                    "reason": _text(p.get("reason"), "reason", 120)})
    return sorted(out, key=lambda p: p["from"])


CRITERIA = tuple(f"C{i}" for i in range(1, 10))


def clean_clinical(c: dict[str, Any], risk_ids: list[str], track_keys: list[str]) -> dict[str, Any]:
    criteria = []
    for k in c.get("criteria") or []:
        if k not in CRITERIA:
            raise ValueError(f"unknown criterion {k!r}")
        if k not in criteria:
            criteria.append(k)
    focus = {}
    for rid, v in (c.get("focus") or {}).items():
        if rid not in risk_ids:
            raise ValueError(f"unknown risk {rid!r}")
        sens = (v or {}).get("sensitivity", "standard")
        if sens not in SENSITIVITY:
            raise ValueError(f"sensitivity must be one of {', '.join(SENSITIVITY)}")
        focus[rid] = {"enabled": bool((v or {}).get("enabled", True)), "sensitivity": sens}
    normals = {}
    for k, v in (c.get("normals") or {}).items():
        if k not in track_keys:
            raise ValueError(f"unknown track {k!r}")
        lo, hi = (v or {}).get("min"), (v or {}).get("max")
        if lo is None and hi is None:
            continue
        try:
            lo = None if lo is None else float(lo)
            hi = None if hi is None else float(hi)
        except (TypeError, ValueError):
            raise ValueError(f"{k}: normal range must be numbers")
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(f"{k}: minimum above maximum")
        normals[k] = {"min": lo, "max": hi}
    return {"history": _text(c.get("history"), "history"), "concerns": _text(c.get("concerns"), "concerns"),
            "treatment": _text(c.get("treatment"), "treatment"), "criteria": criteria,
            "focus": focus, "normals": normals}


class CareStore:
    def __init__(self, home: Path):
        self.path = Path(home) / "care.json"

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def get(self, pid: str) -> dict[str, Any]:
        c = self._load().get(pid, {})
        return {"routine": c.get("routine"), "away_periods": c.get("away_periods", []),
                "clinical": c.get("clinical"), "updated": c.get("updated", {})}

    def _put(self, pid: str, key: str, value: Any, author: str) -> dict[str, Any]:
        with _lock:
            data = self._load()
            entry = data.setdefault(pid, {})
            entry[key] = value
            entry.setdefault("updated", {})[key] = {"by": author, "at": _now()}
            self._save(data)
        return self.get(pid)

    def set_routine(self, pid: str, routine: dict[str, Any], author: str, keep_links: bool) -> dict[str, Any]:
        r = clean_routine(routine)
        if keep_links:      # the patient cannot change the links a clinician made
            old = {d["id"]: d.get("ip") for d in (self.get(pid)["routine"] or {}).get("devices", [])}
            for d in r["devices"]:
                d["ip"] = old.get(d["id"])
        return self._put(pid, "routine", r, author)

    def set_away(self, pid: str, periods: list[dict[str, Any]], author: str) -> dict[str, Any]:
        return self._put(pid, "away_periods", clean_away(periods), author)

    def set_clinical(self, pid: str, clinical: dict[str, Any], author: str, risk_ids: list[str],
                     track_keys: list[str]) -> dict[str, Any]:
        return self._put(pid, "clinical", clean_clinical(clinical, risk_ids, track_keys), author)


def day_type(routine: dict[str, Any] | None, away: list[dict[str, Any]], day: str) -> str | None:
    """'away_period' (holiday, hospital), else the routine's type of that weekday, else None."""
    if any(p["from"] <= day <= p["to"] for p in away):
        return "away_period"
    if not routine:
        return None
    return routine["week"].get(WEEKDAYS[date.fromisoformat(day).weekday()])
