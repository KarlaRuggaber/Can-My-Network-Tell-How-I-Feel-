"""The assistant helps with onboarding and the care plan: it turns free text into suggestions.

- *Routine* (patient onboarding): "I go to school Monday to Friday, Wednesdays online, mostly in bed by
  11..." becomes the weekday types, usual times and named devices of the routine form.
- *Focus* (clinician): the history and current concerns become suggested criteria (with what the
  network can tell about each), the risks to flag and their sensitivity, each with a reason.

Suggestions only fill the forms; nothing is saved until a person reviews and saves them. They use the
model configured under Settings → Assistant (Claude or a local model, with structured output), and every answer is
validated before it reaches the browser.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import care as care_mod, llm
from .observability import OBSERVABILITY, RISK_CRITERIA

_TIME = {"anyOf": [{"type": "string", "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"}, {"type": "null"}]}

ROUTINE_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False,
    "required": ["week", "away_from", "away_to", "bedtime", "wake", "bedtime_free", "wake_free", "devices", "note"],
    "properties": {
        "week": {"type": "object", "additionalProperties": False, "required": list(care_mod.WEEKDAYS),
                 "properties": {d: {"type": "object", "additionalProperties": False, "required": list(care_mod.HALVES),
                                    "properties": {h: {"type": "string", "enum": list(care_mod.DAY_TYPES)}
                                                   for h in care_mod.HALVES}}
                                for d in care_mod.WEEKDAYS}},
        "away_from": _TIME, "away_to": _TIME, "bedtime": _TIME, "wake": _TIME, "bedtime_free": _TIME, "wake_free": _TIME,
        "devices": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "kind", "shared"],
            "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": list(care_mod.DEVICE_KINDS)},
                           "shared": {"type": "boolean"}}}},
        "note": {"type": "string"},
    },
}


def focus_schema(risk_ids: list[str]) -> dict[str, Any]:
    return {
        "type": "object", "additionalProperties": False, "required": ["criteria", "risks", "caveats"],
        "properties": {
            "criteria": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["criterion", "priority", "reason"],
                "properties": {"criterion": {"type": "string", "enum": list(care_mod.CRITERIA)},
                               "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                               "reason": {"type": "string"}}}},
            "risks": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["id", "enabled", "sensitivity", "reason"],
                "properties": {"id": {"type": "string", "enum": risk_ids}, "enabled": {"type": "boolean"},
                               "sensitivity": {"type": "string", "enum": list(care_mod.SENSITIVITY)},
                               "reason": {"type": "string"}}}},
            "caveats": {"type": "array", "items": {"type": "string"}},
        },
    }


ROUTINE_SYSTEM = """\
You fill in the routine form of a research prototype that looks at a person's home-network use.
From the person's own description, set for each weekday, separately for the morning ("am", until
about noon) and the afternoon ("pm"), whether it is spent "away" (school, work, training away from
home), at "home" (home office, online school, working or studying at home) or "free" (weekend, day
off, nothing scheduled). Example: school on Monday morning and nothing in the afternoon is
{"am": "away", "pm": "free"}. Also the usual times away (on away days), bedtime and waking on
away/home days and on free days (HH:MM, 24 h); and the devices they use in plain words with a kind
and whether others share the device. Days or halves not mentioned: Monday-Friday "away", weekend "free".

Times: fill in every clock time the person gives, read in context, and convert it to HH:MM, 24 h.
Leaving home is in the morning unless they say otherwise ("9:30" = 09:30). "Back" or "home again" is
usually afternoon or evening ("back at 6" = 18:00, "6 p.m." = 18:00). Bedtime is evening or night
("11" = 23:00, "half past 12" = 00:30). Waking is in the morning ("7" = 07:00). Approximate times
("around 7") are fine. Leave a time null only when the person gives no time for it; do not invent
times or devices the person does not mention.

"note" is only for facts about the person's week that do not fit the form, written as a short plain
statement in the person's own terms, for example "Every second weekend with my father." At most
two sentences. The note must never describe the form, the question, what was or was not mentioned,
defaults, assumptions, interpretations or transcription errors, and never repeats what is already in
the week, the times or the devices. Use an empty string when there is nothing extra.

The text may be dictated and contain transcription slips ("phone in the laptop" means "phone and
laptop"); read it as meant, silently. The text may also be the answer to one follow-up question
("Question: ... Answer: ..."); then fill in what the answer says (read with the question) and leave
everything else null or at the default.
"""

FOCUS_SYSTEM = """\
You help a clinician set up network-based monitoring for one patient in a research prototype. The
prototype only sees home-network metadata (when and how much devices are in use, which sites are
contacted by hostname; no content, no search terms) and relates it to the DSM-5 criteria C1-C9.

From the clinician's history, concerns and treatment notes, suggest:
- the criteria worth focusing on, each with a priority and a short reason that names what in the
  notes points to it. Use the observability table: say when a relevant criterion can barely be seen
  from the network (level "none") and should be followed with questionnaires or interviews instead;
- which observed risks to flag (the list gives the criteria each speaks to) and how sensitively:
  "strict" for what the notes make likely or dangerous, "standard" otherwise, "relaxed" or disabled
  where the notes give an ordinary explanation (e.g. shift work for later nights);
- caveats: confounds from the notes (school schedule, shared devices, holidays) and limits.
Never switch off "sensitive_sites" (crisis or self-harm sites): it is a safety signal that stays on even
when no suicidal thoughts are reported; you may suggest its sensitivity. Never diagnose and do not
add facts that are not in the notes. Answer in English.
"""


def complete_json(cfg: dict[str, Any], system: str, user: str, schema: dict[str, Any],
                  client: Any = None) -> dict[str, Any]:
    """One structured answer from the configured provider (raises ValueError with a short reason)."""
    return llm.complete_json(cfg, system, user, schema, client)


def suggest_routine(cfg: dict[str, Any], text: str, **clients: Any) -> dict[str, Any]:
    """The routine form filled in from a description, plus `missing`: the follow-up questions for what
    the description left open (see `missing_fields`). The form ignores `missing` when it is saved."""
    raw = complete_json(cfg, ROUTINE_SYSTEM, f"<description>\n{text}\n</description>", ROUTINE_SCHEMA, **clients)
    raw = {**raw, "note": clean_note(raw.get("note"))}
    for field, value in times_from_answer(text, raw).items():   # a clear time the model left out
        if not raw.get(field):
            raw[field] = value
    routine = care_mod.clean_routine(raw)     # validated like a routine typed in by hand
    return {**routine, "missing": missing_fields(routine)}


# ---- the note: facts about the week only ------------------------------------------------------------

_META = re.compile(
    r"\b(users?|the person|this person|person's|provided|mention(?:s|ed|ing)?|not specified|unspecified|"
    r"not (?:given|stated|said|clear)|defaults?|defaulting|instructions?|interpret\w*|transcription|"
    r"questions?|likely|assum\w*|the text|the description|form|null)\b", re.I)
NOTE_MAX = 300


def clean_note(note: Any) -> str:
    """Keep only the sentences of a note that state a fact about the week: the model sometimes writes its
    reasoning there ("User mentions ...", "defaulting to ..."), which is dropped."""
    if not isinstance(note, str):
        return ""
    kept = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", note.strip()) if s.strip() and not _META.search(s)]
    out = ""
    for s in kept:
        if out and len(out) + 1 + len(s) > NOTE_MAX:
            break
        out = f"{out} {s}".strip()
    if len(out) > NOTE_MAX:
        out = out[:NOTE_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "."
    return out


# ---- follow-up questions: what a description of the week left open --------------------------------
# Decided by rules, not by the model: the model only fills the form from the answers.

_WORKDAYS = ("away", "home")
DEFAULT_WEEK = {d: {h: ("free" if d in ("sat", "sun") else "away") for h in care_mod.HALVES} for d in care_mod.WEEKDAYS}


# question texts per id: (both missing, only the first, only the second)
QUESTIONS: dict[str, tuple[str, str, str]] = {
    "away_times": ("On school or work days, when do you usually leave home, and when are you back?",
                   "On school or work days, when do you usually leave home?",
                   "On school or work days, when are you usually back home?"),
    "sleep_workdays": ("On school or work days, when do you usually go to bed, and when do you get up?",
                       "When do you usually go to bed on school or work days?",
                       "When do you usually get up on school or work days?"),
    "sleep_free": ("On weekends and other free days, when do you usually go to bed, and when do you get up?",
                   "When do you usually go to bed on weekends and other free days?",
                   "When do you usually get up on weekends and other free days?"),
}
_PAIRS = {"away_times": ("away_from", "away_to"), "sleep_workdays": ("bedtime", "wake"),
          "sleep_free": ("bedtime_free", "wake_free")}
WEEK_QUESTION = ("Which days are you away for school or work, which do you spend at home, and which are free? "
                 "For example: school Monday to Friday, Wednesday afternoons at home, weekends free.")
DEVICES_QUESTION = ("Which devices do you use at home, for example a phone, a laptop or a tablet? "
                    "Do you share any of them with others?")

# the time questions by their exact text -> the fields they ask for
TIME_QUESTIONS: dict[str, list[str]] = {}
for _qid, (_both, _first, _second) in QUESTIONS.items():
    _a, _b = _PAIRS[_qid]
    TIME_QUESTIONS.update({_both: [_a, _b], _first: [_a], _second: [_b]})


def _pair(routine: dict[str, Any], qid: str) -> list[dict[str, Any]]:
    """One question for two times (e.g. bedtime and waking): both missing, or just the one that is."""
    a, b = _PAIRS[qid]
    miss = [k for k in (a, b) if not routine.get(k)]
    if not miss:
        return []
    both, only_a, only_b = QUESTIONS[qid]
    text = both if len(miss) == 2 else (only_a if miss == [a] else only_b)
    return [{"id": qid, "fields": miss, "question": text}]


def missing_fields(routine: dict[str, Any]) -> list[dict[str, Any]]:
    """What the routine still lacks, as plain-language questions in the order they are asked.

    Each item is {"id", "fields", "question"}: `fields` are the routine keys the answer fills in.
    Missing: the week still exactly at the default (Mon-Fri away, weekend free: maybe never said),
    the times away when a day is away, bedtime and waking for school/work days and for free days
    (each only if such days exist), and no devices.
    """
    week = care_mod.clean_routine({"week": routine.get("week") or {}})["week"]
    kinds = {t for d in week.values() for t in d.values()}
    out: list[dict[str, Any]] = []
    if week == DEFAULT_WEEK:
        out.append({"id": "week", "fields": ["week"], "question": WEEK_QUESTION})
    if "away" in kinds:
        out += _pair(routine, "away_times")
    if kinds & set(_WORKDAYS):
        out += _pair(routine, "sleep_workdays")
    if "free" in kinds:
        out += _pair(routine, "sleep_free")
    if not routine.get("devices"):
        out.append({"id": "devices", "fields": ["devices"], "question": DEVICES_QUESTION})
    return out


# ---- times from a follow-up answer: a conservative fallback when the model left them out ----------------

_FOLLOW_UP = re.compile(r"^\s*Question:\s*(.*?)\s*\n\s*Answer:\s*(.*)$", re.S)
def _ampm(name: str) -> str:
    return r"(?P<" + name + r">[ap]\.?\s?m\b\.?)"


_CUE = r"(?:at|around|about|by|until|till|til|from|to|before|after|approx\.?|~)"
_TIME_RE = re.compile(
    r"(?P<word>\bnoon\b|\bmidnight\b)"
    r"|\b(?P<rel>half past|quarter past|quarter to)\s+(?P<rh>\d{1,2})\b\s*" + _ampm("rap") + r"?"
    r"|\b(?P<h>\d{1,2})\s*(?:[:.]|h\s?)(?P<m>[0-5]\d)\b\s*" + _ampm("ap") + r"?"
    r"|\b(?P<h2>\d{1,2})\s*(?:" + _ampm("ap2") + r"|o'?\s?clock\b|h\b)"
    r"|\b" + _CUE + r"\s+(?P<h3>\d{1,2})\b(?!\s*(?:[:.]\d|[ap]\.?\s?m\b|o'?\s?clock|h\b|days?|hours?|hrs?|minutes?|mins?|weeks?|times?|nights?|x\b|years?|people|%))",
    re.I)
_BACK_CUE = re.compile(r"(back|home again|return\w*|get home|until|till|til|up|wake\w*|get up|got up)\W*(?:\w+\W+){0,2}$", re.I)


def _marker(m: re.Match[str], *names: str) -> str | None:
    for n in names:
        if m.group(n):
            return "a" if m.group(n)[0].lower() == "a" else "p"
    return None


def _raw_times(answer: str) -> list[tuple[int, int, str | None, int]]:
    """(hour, minute, 'a'/'p'/None, position) for each clear clock time in the answer, in order."""
    found: list[tuple[int, int, str | None, int]] = []
    for m in _TIME_RE.finditer(answer):
        if m.group("word"):
            found.append((12 if m.group("word").lower() == "noon" else 0, 0, "x", m.start()))
        elif m.group("rel"):
            h, rel = int(m.group("rh")), m.group("rel").lower()
            if not 0 <= h <= 24:
                continue
            mark = _marker(m, "rap")
            if rel == "half past":
                found.append((h % 24, 30, mark, m.start()))
            elif rel == "quarter past":
                found.append((h % 24, 15, mark, m.start()))
            else:
                found.append(((h - 1) % 24, 45, mark, m.start()))
        elif m.group("h") is not None:
            found.append((int(m.group("h")), int(m.group("m")), _marker(m, "ap"), m.start()))
        elif m.group("h2") is not None:
            found.append((int(m.group("h2")), 0, _marker(m, "ap2"), m.start()))
        elif m.group("h3") is not None:
            found.append((int(m.group("h3")), 0, None, m.start()))
    return [t for t in found if 0 <= t[0] <= 23]


def _resolve(field: str, h: int, m: int, mark: str | None, leave: int | None) -> str | None:
    if mark == "x":                                   # noon / midnight
        pass
    elif h > 12:
        pass                                          # already 24 h
    elif mark == "a":
        h = 0 if h == 12 else h
    elif mark == "p":
        h = h if h == 12 else h + 12
    elif field in ("away_from", "wake", "wake_free"):
        pass                                          # morning
    elif field == "away_to":
        if h < 12 and (h <= 7 or (leave is not None and h * 60 + m <= leave)):
            h += 12
    elif field in ("bedtime", "bedtime_free"):
        if 6 <= h <= 11:
            h += 12
        elif h == 12:
            h = 0
    return f"{h:02d}:{m:02d}" if 0 <= h <= 23 else None


def parse_times(answer: str, fields: list[str], leave: str | None = None) -> dict[str, str]:
    """Clock times in `answer` for the asked `fields`: the first time for the first field, the second for
    the second. Only clear times count ("9:30", "6 p.m.", "half past 12", "around 7"), not bare numbers."""
    times = _raw_times(answer)
    if not times or not fields:
        return {}
    chosen = times[:len(fields)]
    targets = list(fields)
    if len(fields) == 2 and len(chosen) == 1 and _BACK_CUE.search(answer[:chosen[0][3]]):
        targets = fields[1:]                          # one time, said as "back at ..." / "up at ..."
    leave_min = None
    if leave and re.fullmatch(r"\d\d:\d\d", leave):
        leave_min = int(leave[:2]) * 60 + int(leave[3:])
    out: dict[str, str] = {}
    for field, (h, m, mark, _pos) in zip(targets, chosen):
        value = _resolve(field, h, m, mark, leave_min)
        if value:
            out[field] = value
            if field == "away_from":
                leave_min = int(value[:2]) * 60 + int(value[3:])
    return out


def times_from_answer(text: str, raw: dict[str, Any]) -> dict[str, str]:
    """For a follow-up ("Question: ...\nAnswer: ...") to one of the time questions: the times the answer
    gives for the fields the model left empty."""
    m = _FOLLOW_UP.match(text or "")
    fields = TIME_QUESTIONS.get(m.group(1).strip()) if m else None
    if not m or not fields:
        return {}
    found = parse_times(m.group(2), fields, raw.get("away_from"))
    return {f: v for f, v in found.items() if not raw.get(f)}


def suggest_focus(cfg: dict[str, Any], clinical_text: dict[str, str], routine: dict[str, Any] | None,
                  risks: list[dict[str, str]], **clients: Any) -> dict[str, Any]:
    risk_ids = [r["id"] for r in risks]
    user = json.dumps({
        "clinician_notes": clinical_text,
        "patient_routine": routine,
        "observability_per_criterion": {c: {"level": v["level"], "observes": v["observes"], "cannot": v["cannot"]}
                                        for c, v in OBSERVABILITY.items()},
        "observed_risks": [{**r, "criteria": RISK_CRITERIA.get(r["id"], [])} for r in risks],
    }, ensure_ascii=False)
    raw = complete_json(cfg, FOCUS_SYSTEM, user, focus_schema(risk_ids), **clients)
    crit = [c for c in raw.get("criteria", []) if c.get("criterion") in care_mod.CRITERIA]
    rk = [r for r in raw.get("risks", []) if r.get("id") in risk_ids and r.get("sensitivity") in care_mod.SENSITIVITY]
    for r in rk:   # a safety signal: a suggestion never switches it off (a clinician can, by hand)
        if r["id"] == "sensitive_sites" and not r.get("enabled"):
            r["enabled"] = True
            r["reason"] = f"Kept on as a safety signal. {r.get('reason', '')}".strip()
    return {"criteria": crit, "risks": rk, "caveats": [str(c) for c in raw.get("caveats", [])][:8]}
