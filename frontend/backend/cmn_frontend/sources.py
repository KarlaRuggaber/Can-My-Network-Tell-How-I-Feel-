"""\"Based on\": which data of the context an assistant answer used.

The model ends every answer with a hidden block

    <based_on>{"days": [...], "metrics": [...], "criteria": [...], "flags": [...]}</based_on>

copied from the <results> context of that request. This module

1. keeps the block out of the visible stream (BasedOnSplitter; the tag may be split across chunks, the
   closing tag may be missing, the block may be missing altogether),
2. validates the block against that same context (nothing the context does not contain survives),
3. enriches each surviving item with its display name, unit and numbers *from the context* (the model
   never supplies a number), and
4. appends one final record to the text stream: RECORD_SEP (ASCII 0x1E) followed by the JSON
   {"items": [...], "fallback": bool, "no_data": bool}.

Identifiers the model returns (all literally present in the context JSON):
  days      "2025-11-04"                         the dates of context["days"]
  metrics   "quiet_hours", "hours_in_use", ...   the keys of observed_behaviour.days[date]
            or a scored metric's name exactly as in "parts" / "baseline_mean_sd_of_metrics"
  criteria  "C4 Sleep" (clinician) / "Sleep" (person)   the entries of "criteria" / "areas"
  flags     "later_nights"                        the "id" of observed_behaviour.flags
The person view never gets a criterion code in the output: criteria are area names only.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Iterable, Iterator

RECORD_SEP = "\x1e"
TAG = "<based_on"
CLOSE_TAG = "</based_on>"

MAX_ITEMS = {"days": 3, "metrics": 4, "criteria": 3, "flags": 2}
MAX_VALUE_DAYS = 3       # values shown per metric / criterion


# ---- the stream filter ------------------------------------------------------------------------------

class BasedOnSplitter:
    """Visible text and hidden remainder of a streamed answer.

    feed(chunk) returns the text that may be shown now. From "<based_on" on, everything is kept in
    `hidden`. A tail that could still turn into the tag ("...<bas") and trailing whitespace are held
    back until the next chunk decides; at the end, finish() releases a held tail that never became the
    tag and drops whitespace that only preceded the block (or ended the answer)."""

    def __init__(self) -> None:
        self.hidden: str | None = None
        self._buf = ""

    def feed(self, chunk: str) -> str:
        if self.hidden is not None:
            self.hidden += chunk
            return ""
        self._buf += chunk
        i = self._buf.find(TAG)
        if i >= 0:
            self.hidden = self._buf[i:]
            out, self._buf = self._buf[:i], ""
            return out.rstrip()
        # hold back a suffix that could still become the tag, then trailing whitespace
        keep = 0
        for n in range(min(len(TAG) - 1, len(self._buf)), 0, -1):
            if TAG.startswith(self._buf[-n:]):
                keep = n
                break
        head, tail = self._buf[:len(self._buf) - keep], self._buf[len(self._buf) - keep:]
        stripped = head.rstrip()
        self._buf = head[len(stripped):] + tail
        return stripped

    def finish(self) -> str:
        out = "" if self.hidden is not None else self._buf.rstrip()
        self._buf = ""
        return out


def split_based_on(text: str) -> tuple[str, str | None]:
    """A whole answer: (visible text, hidden block text or None)."""
    sp = BasedOnSplitter()
    visible = sp.feed(text) + sp.finish()
    return visible, sp.hidden


def parse_block(hidden: str | None) -> dict[str, list[Any]] | None:
    """The JSON of a hidden block; None when it is missing or not an object. A missing closing tag, a
    code fence or trailing text around the JSON are tolerated."""
    if not hidden:
        return None
    body = re.sub(r"^<based_on\s*>", "", hidden.strip())
    body = body.split(CLOSE_TAG)[0]
    start = body.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(body[start:])
    except ValueError:
        return None
    if not isinstance(obj, dict):
        return None
    return {k: (obj.get(k) if isinstance(obj.get(k), list) else []) for k in MAX_ITEMS}


# ---- formatting -------------------------------------------------------------------------------------

def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _fmt_h(v: float) -> str:
    """Hours with one decimal at most ("4.6", "16.5", "8")."""
    return f"{round(v, 1):g}"


def _fmt_n(v: float) -> str:
    """A value rounded for reading: whole from 100, 1 decimal from 10, else 2 ("1094", "16.5", "0.24")."""
    a = abs(v)
    return f"{round(v, 0 if a >= 100 else 1 if a >= 10 else 2):g}"


def _fmt(v: float) -> str:
    """2 decimals at most, no trailing zeros ("5.2", "0.62", "12")."""
    return f"{round(v, 2):g}"


def _clock(m: Any) -> str | None:
    v = _num(m)
    if v is None:
        return None
    m = int(round(v))
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def _norm(s: Any) -> str:
    return " ".join(str(s).casefold().split())


# observed tracks: name in observed_behaviour.days -> (key in observed_behaviour.usual, unit)
OBSERVED = {
    "went_quiet": ("quiet_start", "clock"), "back_online": ("quiet_end", "clock"),
    "quiet_hours": ("quiet_hours", "h"), "hours_in_use": ("online_hours", "h"),
    "minutes_in_use_at_night": ("night_minutes", "min"),
    "chat_sessions": ("chat_sessions", "count"), "different_sites": ("sites", "count"),
}


def _track_meta(name: str) -> tuple[str, str | None]:
    """Display label and icon of an observed track (the portal's own wording)."""
    from .observed import TRACK_BY_KEY
    t = TRACK_BY_KEY.get(OBSERVED[name][0])
    return (t.label, t.icon or None) if t else (name.replace("_", " ").capitalize(), None)


def _show(unit: str, v: Any) -> str | None:
    if unit == "clock":
        return v if isinstance(v, str) else None
    n = _num(v)
    if n is None:
        return None
    if unit == "h":
        return f"{_fmt_h(n)} h"
    if unit == "min":
        return f"{int(round(n))} min"
    return str(int(round(n)))


def _usual(unit: str, u: dict[str, Any] | None) -> str | None:
    """The usual range (mean +/- 1 SD of the baseline days) in the track's unit."""
    mean, sd = _num((u or {}).get("mean")), _num((u or {}).get("sd"))
    if mean is None or sd is None:
        return None
    lo, hi = mean - sd, mean + sd
    if unit == "clock":
        a, b = _clock(lo), _clock(hi)
        return f"{a} to {b}" if a and b else None
    lo = max(lo, 0.0)
    if unit == "h":
        return f"{_fmt_h(lo)} to {_fmt_h(hi)} h"
    if unit == "min":
        return f"{int(round(lo))} to {int(round(hi))} min"
    return f"{int(round(lo))} to {int(round(hi))}"


def _unit_of_label(label: str) -> str:
    m = re.search(r"\((min|h|s)\)\s*$", label)
    return m.group(1) if m else ""


# ---- the context index ------------------------------------------------------------------------------

class _Index:
    """What a request's context contains, for validation and the values of each item."""

    def __init__(self, ctx: dict[str, Any], person_view: bool, labels: dict[str, str] | None = None):
        self.person = person_view
        self.rows: dict[str, dict[str, Any]] = {r["date"]: r for r in ctx.get("days", []) if r.get("date")}
        obs = ctx.get("observed_behaviour") or {}
        self.obs_days: dict[str, dict[str, Any]] = obs.get("days") or {}
        self.usual: dict[str, Any] = obs.get("usual") or {}
        self.flags: list[dict[str, Any]] = [f for f in obs.get("flags", []) if f.get("id")]
        self.baseline: dict[str, Any] = ctx.get("baseline_mean_sd_of_metrics") or {}
        self.periods: dict[str, Any] = ctx.get("periods") or {}
        # criteria: context name ("C4 Sleep" / "Sleep") -> code
        names = list(ctx.get("areas" if person_view else "criteria") or [])
        if not person_view:
            names += list((ctx.get("unscored_criteria") or {}).get("criteria") or [])
        self.criteria: dict[str, str | None] = {}
        for n in names:
            m = re.match(r"^(C[1-9])\b", n)
            self.criteria[n] = m.group(1) if m else _code_of_area(n)
        self.dates = set(self.rows) | set(self.obs_days)
        # scored metrics: names as they appear in the context
        self.scored: set[str] = set(self.baseline)
        for row in self.rows.values():
            for parts in (row.get("parts") or {}).values():
                self.scored.update(parts)
        self.code_of = {} if (person_view or not labels) else {v: k for k, v in labels.items()}
        self.tracks = {n for n in OBSERVED if any(n in d for d in self.obs_days.values())}
        # lookup tables (normalised -> canonical)
        self.metric_lookup: dict[str, tuple[str, str]] = {}
        for n in self.tracks:
            key, label = OBSERVED[n][0], _track_meta(n)[0]
            for alias in (n, key, label):
                self.metric_lookup.setdefault(_norm(alias), ("track", n))
        for s in self.scored:
            self.metric_lookup.setdefault(_norm(s), ("scored", s))
        self.criterion_lookup: dict[str, str] = {}
        for n, code in self.criteria.items():
            self.criterion_lookup.setdefault(_norm(n), n)
            if code:       # a bare code resolves too; the person view only ever shows the area name
                self.criterion_lookup.setdefault(_norm(code), n)
        self.flag_lookup = {_norm(f["id"]): f for f in self.flags}
        for f in self.flags:
            self.flag_lookup.setdefault(_norm(f.get("title", "")), f)

    def latest_day(self, test: Any = None) -> str | None:
        for d in sorted(self.dates, reverse=True):
            if test is None or test(d):
                return d
        return None


def _code_of_area(name: str) -> str | None:
    from .assistant import AREA_NAMES
    return next((c for c, n in AREA_NAMES.items() if n == name), None)


# ---- validation and enrichment ----------------------------------------------------------------------

def _dedupe(seq: Iterable[Any]) -> list[Any]:
    out: list[Any] = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def _day_item(ix: _Index, date: str) -> dict[str, Any]:
    row = ix.rows.get(date) or {}
    bits = [b for b in (row.get("weekday"), row.get("period")) if b]
    return {"kind": "day", "id": date, "name": date, "icon": None, "unit": None, "values": [], "usual": None,
            "detail": ", ".join(bits) or None, "code": None, "days": [date]}


def _track_item(ix: _Index, name: str, days: list[str]) -> dict[str, Any]:
    key, unit = OBSERVED[name]
    label, icon = _track_meta(name)
    show = [d for d in days if _show(unit, (ix.obs_days.get(d) or {}).get(name)) is not None][:MAX_VALUE_DAYS]
    if not show and not days:
        last = ix.latest_day(lambda d: _show(unit, (ix.obs_days.get(d) or {}).get(name)) is not None)
        show = [last] if last else []
    vals = [{"day": d, "text": _show(unit, ix.obs_days[d][name])} for d in show]
    return {"kind": "metric", "id": name, "name": label, "icon": icon, "unit": None if unit in ("clock", "count") else unit,
            "values": vals, "usual": _usual(unit, ix.usual.get(key)), "detail": None, "code": None,
            "days": [v["day"] for v in vals]}


def _scored_item(ix: _Index, label: str, days: list[str]) -> dict[str, Any]:
    unit = _unit_of_label(label)

    def part(d: str) -> dict[str, Any] | None:
        for parts in ((ix.rows.get(d) or {}).get("parts") or {}).values():
            if label in parts and _num(parts[label].get("value")) is not None:
                return parts[label]
        return None

    show = [d for d in days if part(d)][:MAX_VALUE_DAYS]
    if not show and not days:
        last = ix.latest_day(lambda d: part(d) is not None)
        show = [last] if last else []
    f = _fmt_h if unit == "h" else _fmt_n
    vals = [{"day": d, "text": f(_num(part(d)["value"])) + (f" {unit}" if unit else "")} for d in show]
    b = ix.baseline.get(label) or {}
    mean, sd = _num(b.get("mean")), _num(b.get("sd"))
    usual = None
    if mean is not None and sd is not None:
        lo = max(mean - sd, 0.0) if mean >= 0 else mean - sd     # a non-negative metric never shows a range below 0
        usual = f"{f(lo)} to {f(mean + sd)}" + (f" {unit}" if unit else "")
    detail = None
    if show and not ix.person:
        p = part(show[0])
        bits = [f"risk degree {int(_num(p['risk_degree_percent']))} %" if _num(p.get("risk_degree_percent")) is not None else None,
                f"weight {int(_num(p['weight_percent']))} %" if _num(p.get("weight_percent")) is not None else None]
        detail = ", ".join(b for b in bits if b) or None
    name = label[:1].upper() + label[1:] if ix.person else label       # person: everyday phrase, sentence case
    return {"kind": "metric", "id": ix.code_of.get(label, label), "name": name, "icon": None, "unit": unit or None,
            "values": vals, "usual": usual, "detail": detail, "code": ix.code_of.get(label),
            "days": [v["day"] for v in vals]}


def _criterion_item(ix: _Index, ctx_name: str, days: list[str]) -> dict[str, Any]:
    code = ix.criteria.get(ctx_name)
    if ix.person:        # everyday area name, no code and no scores
        return {"kind": "criterion", "id": ctx_name, "name": ctx_name, "icon": None, "unit": None, "values": [],
                "usual": None, "detail": None, "code": None, "days": []}
    def prob(d: str) -> float | None:
        return _num(((ix.rows.get(d) or {}).get("probability_percent") or {}).get(ctx_name))

    show = [d for d in days if prob(d) is not None][:MAX_VALUE_DAYS]
    if not show and not days:
        last = ix.latest_day(lambda d: prob(d) is not None)
        show = [last] if last else []
    vals = [{"day": d, "text": f"probability {int(round(prob(d)))} %"} for d in show]
    present = [f"{ph}: {'present' if r['present'] else 'not present'}" for ph, p in ix.periods.items()
               if isinstance((r := (p.get("results") or {}).get(ctx_name)), dict) and "present" in r]
    base = re.sub(r"^C[1-9]\s+", "", ctx_name)
    return {"kind": "criterion", "id": code or ctx_name, "name": f"{base} ({code})" if code else ctx_name,
            "icon": None, "unit": None, "values": vals, "usual": None,
            "detail": "; ".join(present) or None, "code": code, "days": [v["day"] for v in vals]}


def _flag_item(f: dict[str, Any]) -> dict[str, Any]:
    days = [d for d in f.get("days") or [] if isinstance(d, str)]
    detail = f"{f['count']} of the last {f['of_last']} days" if f.get("count") and f.get("of_last") else None
    return {"kind": "flag", "id": f["id"], "name": f.get("title") or f["id"],
            "icon": "change" if f.get("kind") == "change" else None, "unit": None,
            "values": [{"day": d, "text": ""} for d in days[:MAX_VALUE_DAYS]], "usual": None, "detail": detail,
            "code": None, "days": days[:MAX_VALUE_DAYS]}


def resolve(block: dict[str, list[Any]], ix: _Index) -> tuple[list[dict[str, Any]], int, int]:
    """(items, entries the model listed, entries that matched the context). Order: metrics, criteria,
    flags, days; duplicates and entries beyond the per-kind caps are not counted as unknown."""
    listed = matched = 0

    def strings(kind: str) -> list[str]:
        nonlocal listed
        out = [s.strip() for s in block.get(kind, []) if isinstance(s, str) and s.strip()]
        listed += len([x for x in block.get(kind, []) if x not in (None, "")])
        return out

    days = []
    for s in strings("days"):
        if s in ix.dates:
            days.append(s)
            matched += 1
    days = _dedupe(days)
    items: list[dict[str, Any]] = []
    mets = []
    for s in strings("metrics"):
        hit = ix.metric_lookup.get(_norm(s))
        if hit:
            mets.append(hit)
            matched += 1
    for kind, name in _dedupe(mets)[:MAX_ITEMS["metrics"]]:
        items.append(_track_item(ix, name, days) if kind == "track" else _scored_item(ix, name, days))
    crits = []
    for s in strings("criteria"):
        hit = ix.criterion_lookup.get(_norm(s))
        if hit:
            crits.append(hit)
            matched += 1
    items += [_criterion_item(ix, n, days) for n in _dedupe(crits)[:MAX_ITEMS["criteria"]]]
    flags = []
    for s in strings("flags"):
        hit = ix.flag_lookup.get(_norm(s))
        if hit:
            flags.append(hit)
            matched += 1
    seen: set[str] = set()
    for f in flags:
        if f["id"] not in seen and len(seen) < MAX_ITEMS["flags"]:
            seen.add(f["id"])
            items.append(_flag_item(f))
    items += [_day_item(ix, d) for d in days[:MAX_ITEMS["days"]]]
    return items, listed, matched


def focus_items(focus: str | None, ix: _Index) -> list[dict[str, Any]]:
    """Fallback sources: the day and the criterion (or flag) the screen was showing."""
    if not focus:
        return []
    items: list[dict[str, Any]] = []
    m = re.match(r"^flag (\S+)", focus)
    if m and _norm(m.group(1)) in ix.flag_lookup:
        items.append(_flag_item(ix.flag_lookup[_norm(m.group(1))]))
    c = re.search(r"\b(C[1-9])\b", focus)
    if c:
        name = ix.criterion_lookup.get(_norm(c.group(1)))
        if name:
            items.append(_criterion_item(ix, name, []))
    d = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", focus)
    if d and d.group(1) in ix.dates:
        items.append(_day_item(ix, d.group(1)))
    return items


def sources_record(hidden: str | None, ctx: dict[str, Any], person_view: bool, focus: str | None = None,
                   labels: dict[str, str] | None = None) -> dict[str, Any]:
    """The final record: {"items": [...], "fallback": bool, "no_data": bool}.

    Block missing or not JSON, or nothing in it matches the context: fallback to the focus. A valid block
    that lists nothing (a general question): no_data."""
    ix = _Index(ctx, person_view, labels)
    block = parse_block(hidden)
    if block is not None:
        items, listed, matched = resolve(block, ix)
        if listed == 0:
            return {"items": [], "fallback": False, "no_data": True}
        if items:
            return {"items": items, "fallback": False, "no_data": False}
    return {"items": focus_items(focus, ix), "fallback": True, "no_data": False}


def answer_stream(chunks: Iterable[str], ctx: dict[str, Any], person_view: bool, focus: str | None = None,
                  labels: dict[str, str] | None = None, guard: Any = None) -> Iterator[str]:
    """The text of the answer without the hidden block (through `guard`, e.g. assistant.guard_person,
    when given), then one record: RECORD_SEP + JSON of sources_record()."""
    sp = BasedOnSplitter()

    def visible() -> Iterator[str]:
        for c in chunks:
            t = sp.feed(c)
            if t:
                yield t
        t = sp.finish()
        if t:
            yield t

    yield from (guard(visible()) if guard else visible())
    yield RECORD_SEP + json.dumps(sources_record(sp.hidden, ctx, person_view, focus, labels), ensure_ascii=False,
                                  separators=(",", ":"))


def listed_unknown(hidden: str | None, ctx: dict[str, Any], person_view: bool) -> dict[str, Any]:
    """For the eval: did the answer carry a parsable block, and did every entry exist in the context?"""
    block = parse_block(hidden)
    if block is None:
        return {"valid": False, "unknown": 0, "listed": 0, "codes": []}
    ix = _Index(ctx, person_view)
    items, listed, matched = resolve(block, ix)
    codes = [it["name"] for it in items if person_view and re.search(r"\bC[1-9]\b", f"{it['name']} {it['id']} {it.get('code') or ''}")]
    return {"valid": True, "unknown": listed - matched, "listed": listed, "codes": codes}
