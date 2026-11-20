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
away/home days and on free days (HH:MM, 24 h; null when not mentioned); and the devices they use in plain words with a kind
and whether others share the device. Keep a short "note" for anything relevant that does not fit
(e.g. "every second weekend with my father"). Do not invent: leave times null and devices out when
the description does not say. Days or halves not mentioned: Monday-Friday "away", weekend "free".
The text may also be the answer to one follow-up question ("Question: ... Answer: ..."); then fill
in what the answer says (read with the question) and leave everything else null or at the default.
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
    routine = care_mod.clean_routine(raw)     # validated like a routine typed in by hand
    return {**routine, "missing": missing_fields(routine)}


# ---- follow-up questions: what a description of the week left open --------------------------------
# Decided by rules, not by the model: the model only fills the form from the answers.

_WORKDAYS = ("away", "home")
DEFAULT_WEEK = {d: {h: ("free" if d in ("sat", "sun") else "away") for h in care_mod.HALVES} for d in care_mod.WEEKDAYS}


def _pair(routine: dict[str, Any], qid: str, a: str, b: str, both: str, only_a: str, only_b: str) -> list[dict[str, Any]]:
    """One question for two times (e.g. bedtime and waking): both missing, or just the one that is."""
    miss = [k for k in (a, b) if not routine.get(k)]
    if not miss:
        return []
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
        out.append({"id": "week", "fields": ["week"], "question":
                    "Which days are you away for school or work, which do you spend at home, and which are free? "
                    "For example: school Monday to Friday, Wednesday afternoons at home, weekends free."})
    if "away" in kinds:
        out += _pair(routine, "away_times", "away_from", "away_to",
                     "On school or work days, when do you usually leave home, and when are you back?",
                     "On school or work days, when do you usually leave home?",
                     "On school or work days, when are you usually back home?")
    if kinds & set(_WORKDAYS):
        out += _pair(routine, "sleep_workdays", "bedtime", "wake",
                     "On school or work days, when do you usually go to bed, and when do you get up?",
                     "When do you usually go to bed on school or work days?",
                     "When do you usually get up on school or work days?")
    if "free" in kinds:
        out += _pair(routine, "sleep_free", "bedtime_free", "wake_free",
                     "On weekends and other free days, when do you usually go to bed, and when do you get up?",
                     "When do you usually go to bed on weekends and other free days?",
                     "When do you usually get up on weekends and other free days?")
    if not routine.get("devices"):
        out.append({"id": "devices", "fields": ["devices"], "question":
                    "Which devices do you use at home, for example a phone, a laptop or a tablet? "
                    "Do you share any of them with others?"})
    return out


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
