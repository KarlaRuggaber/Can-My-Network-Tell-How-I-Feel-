"""The assistant helps with onboarding and the care plan: it turns free text into suggestions.

- *Routine* (patient onboarding): "I go to school Monday to Friday, Wednesdays online, mostly in bed by
  11..." becomes the weekday types, usual times and named devices of the routine form.
- *Focus* (clinician): the history and current concerns become suggested criteria (with what the
  network can tell about each), the risks to flag and their sensitivity, each with a reason.

Suggestions only fill the forms; nothing is saved until a person reviews and saves them. They use the
model configured under Settings → Assistant (Claude with structured output), and every answer is
validated before it reaches the browser.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import care as care_mod
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


def _first_json(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("the assistant gave no JSON")
    return json.loads(m.group(0))


def complete_json(cfg: dict[str, Any], system: str, user: str, schema: dict[str, Any],
                  anthropic_client: Any = None) -> dict[str, Any]:
    """One structured answer from Claude (raises ValueError with a short reason)."""
    import anthropic
    client = anthropic_client
    if client is None:
        client = anthropic.Anthropic(api_key=cfg["api_key"]) if cfg["api_key"] else anthropic.Anthropic()
    try:
        msg = client.beta.messages.create(
            model=cfg["model"], max_tokens=8000, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise ValueError("no valid Anthropic credentials (Settings → Assistant)")
    except anthropic.RateLimitError:
        raise ValueError("the assistant is busy, try again in a minute")
    except anthropic.APIStatusError as e:
        raise ValueError(f"the assistant failed ({e.status_code})")
    except anthropic.APIConnectionError:
        raise ValueError("could not reach the Anthropic API")
    if msg.stop_reason == "refusal":
        raise ValueError("the assistant could not answer this")
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return json.loads(text)


def suggest_routine(cfg: dict[str, Any], text: str, **clients: Any) -> dict[str, Any]:
    raw = complete_json(cfg, ROUTINE_SYSTEM, f"<description>\n{text}\n</description>", ROUTINE_SCHEMA, **clients)
    return care_mod.clean_routine(raw)        # validated like a routine typed in by hand


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
