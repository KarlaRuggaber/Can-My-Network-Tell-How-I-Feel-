"""Explanation assistant: answers questions about one profile's computed results, in natural language.

It is an explanation layer only. Claude receives the derived daily results that the portal already
shows (likelihoods per criterion, metric values, membership degrees μ and weights w, baseline mean
and SD, the gate per period) and explains where a finding comes from. It never sees raw packets,
IP addresses, hostnames or device names, and it must not diagnose.

Off by default, because questions and these derived results are sent to an external model API.
A multi-profile user turns it on in the portal (Settings → Assistant): model and Claude API key are
stored in <home>/assistant.json (readable by the owner only; the key is never sent back to a
browser). Environment variables give the defaults:

    CMN_ASSISTANT=1                         # on
    CMN_ASSISTANT_MODEL=claude-sonnet-5-5
    ANTHROPIC_API_KEY=...

The only provider is Anthropic (Claude through the official SDK, with the project's Claude key).

Single-profile users (the person themself) get a context without expectations or clinical labels and
answers in everyday language; multi-profile users (clinicians, parents) get the criterion names and,
for scripted personas, the expected outcomes.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import fasl

PROVIDERS = {
    "anthropic": {"label": "Anthropic (Claude)", "default_model": "claude-sonnet-5-5",
                  "key_env": "ANTHROPIC_API_KEY"},
}
DEFAULT_PROVIDER = "anthropic"
MAX_TURNS = 20

# Everyday names for the scored criteria (person view and person assistant).
AREA_NAMES = {
    "C1": "Daily rhythm",
    "C2": "Variety and social contact",
    "C3": "Appetite-related use",
    "C4": "Sleep",
    "C5": "Restlessness",
    "C6": "Energy",
    "C7": "Self-related browsing",
    "C8": "Focus",
    "C9": "Sensitive searches",
}


# Everyday descriptions of the scored metrics, used instead of the technical labels for the person.
PLAIN_METRICS = {
    "F1_DistinctSocial": "number of different social and messaging sites used",
    "F4_DownUpRatio": "how much was received compared with sent (watching/reading vs. writing)",
    "F6_Fano": "how bursty the activity was over the day",
    "F7_HourlyCV": "how uneven the activity was across the hours of the day",
    "F8_NightDayRatioPkts": "activity at night compared with the day",
    "C2_F1_UniqueSLD": "number of different websites and services used",
    "C2_F3_ChatSessionCount": "number of chat sessions",
    "C2_F4_MeanUpstreamRateBps": "how much was sent (posting, calls, uploads)",
    "C2_F6_ProductivityHits": "use of work and study tools",
    "C4_F2_WakeAfter0400Min": "time of the first activity in the morning (minutes after 04:00)",
    "C4_F4_SleepDurationZAbs30d": "how far the quiet night-time stretch differed from the last weeks",
    "C4_F7_DaytimeIdleRatio0818": "share of quiet time during the day (08:00-18:00)",
    "C4_F8_NightDayTrafficRatioBytes": "data used at night compared with the day",
    "C8_F2_DNSBurstRatePerHour": "how often many websites were opened in quick succession",
    "C8_F4_RepeatedQueryRatio60m": "how often the same sites were opened again within an hour",
    "C8_F8_MedianIKSsec": "typical pause between two actions",
}


class AssistantConfig:
    """Assistant settings: <home>/assistant.json over environment defaults. Claude only."""

    def __init__(self, home: Path):
        self.path = Path(home) / "assistant.json"

    def _file(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def load(self) -> dict[str, Any]:
        f = self._file()
        p = PROVIDERS[DEFAULT_PROVIDER]
        env_on = os.environ.get("CMN_ASSISTANT", "").lower() in ("1", "true", "yes")
        key = (f.get("api_keys") or {}).get(DEFAULT_PROVIDER) or os.environ.get(p["key_env"], "")
        model = (f.get("models") or {}).get(DEFAULT_PROVIDER) or os.environ.get("CMN_ASSISTANT_MODEL") \
            or p["default_model"]
        return {"enabled": bool(f.get("enabled", env_on)), "provider": DEFAULT_PROVIDER, "model": model,
                "api_key": key}

    def public(self) -> dict[str, Any]:
        c = self.load()
        return {"enabled": c["enabled"], "model": c["model"],
                "default_model": PROVIDERS[DEFAULT_PROVIDER]["default_model"],
                "has_key": bool(c["api_key"]) or _anthropic_profile(),
                "notice": (f"Your question and this profile's daily results (no raw traffic, addresses or device "
                           f"names) are sent to Anthropic's Claude ({c['model']}) to write the answer.")}

    def save(self, enabled: bool, model: str, api_key: str | None) -> None:
        """api_key None: keep the stored key; "": remove it. Keys of earlier providers are dropped."""
        model = model.strip()
        if not model or len(model) > 200:
            raise ValueError("model is required")
        f = self._file()
        keys = {k: v for k, v in (f.get("api_keys") or {}).items() if k in PROVIDERS}
        if api_key is not None:
            if api_key.strip():
                keys[DEFAULT_PROVIDER] = api_key.strip()
            else:
                keys.pop(DEFAULT_PROVIDER, None)
        f = {"enabled": bool(enabled), "provider": DEFAULT_PROVIDER, "models": {DEFAULT_PROVIDER: model},
             "api_keys": keys}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(f, fh, indent=1)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)


def _anthropic_profile() -> bool:
    """An `ant auth login` profile also counts as Anthropic credentials."""
    return (Path.home() / ".config" / "anthropic").is_dir()


def _r(x: Any, nd: int = 3) -> Any:
    if isinstance(x, float):
        return round(x, nd) if math.isfinite(x) else None
    return x


SYSTEM_COMMON = """\
You are the explanation assistant of a research prototype, "Can My Network Tell How I Feel?". The
prototype derives daily metrics from a home router's network traffic metadata (packet timing, volume,
DNS lookups; no content) and turns them into likelihoods L between 0 and 1 for DSM-5 depression
criteria with a fuzzy scoring model (FASL): each metric value is mapped to a membership degree μ
between 0 and 1 and weighted with w; L = Σ w·μ, clipped to [0, 1]. A criterion counts as "present" in a
period when L ≥ θ on at least N of the period's last M days. The data you get is in <results>.

Your only job is to explain these results: what a value means, which metrics drove a likelihood on a
day, how a period compares with the baseline, and how the scoring works. Rules:
- Use only the numbers in <results>. Name the metric, the day and the value you rely on. If the data
  does not answer a question, say so plainly. Never invent values.
- This is not a diagnosis and not a medical device. Do not diagnose, do not predict a condition, and do
  not recommend treatment. Network patterns can change for many ordinary reasons (travel, holidays,
  a new device, guests); say so where it matters.
- Keep answers short: a few sentences or a short list. No tables or headings unless asked. Basic
  Markdown (bold, bullet lists) is rendered.
- The data covers scripted test personas or consenting participants; still treat it as personal.
"""

SYSTEM_PERSON = """\
You are talking with the person whose data this is. Write in plain, warm, everyday language.
- Use the everyday area names given in <results> (for example "Sleep", "Daily rhythm"). Do not use
  DSM-5 criterion names, criterion numbers, diagnoses or clinical terms, and do not speculate about
  what a pattern could mean medically.
- Do not tell the person which changes were expected or planned; you do not know that, and it must not
  influence them.
- Do not quote the 0–1 area scores, thresholds, weights or rules like "N of M days", and avoid notation
  (θ, μ, L), unless the person explicitly asks how the scoring works. Say in words how different a day
  was ("a little", "clearly"), and describe what happened in everyday terms ("you were online later than
  usual", "fewer different websites than usual"), with a value only when it helps.
- Formatting: short paragraphs; at most a simple bullet list; **bold** sparingly.
- If the person says they feel unwell, are worried, or mentions self-harm, respond with care, encourage
  them to talk to someone they trust or a professional, and, for urgent danger, mention emergency help
  (in Switzerland: 144, or Die Dargebotene Hand at 143).
"""

SYSTEM_CLINICIAN = """\
You are talking with a clinician, researcher or carer who supervises this person. You may use the
DSM-5 criterion names, the scoring notation and the numbers directly. Where <results> contains
expected outcomes of a scripted persona, you may compare observed with expected, but make clear that
the expectations come from the test script, not from the data.
"""


def build_context(tl: dict[str, Any], cfg: fasl.FaslConfig, person_view: bool,
                  metric_labels: dict[str, str]) -> dict[str, Any]:
    """The data Claude may use, derived from a timeline (no IPs, hostnames or device names)."""
    configured = [c for c in fasl.CRIT_KEYS if cfg.configured(c)]
    if person_view:   # everyday descriptions instead of the metric code's technical labels
        metric_labels = {**metric_labels, **PLAIN_METRICS}
    name_of = (lambda c: AREA_NAMES[c]) if person_view else (lambda c: f"{c} {fasl.CRIT_NAMES[c]}")
    labels = tl["profile"]["phase_labels"]
    gate = tl["gate"]
    periods = {}
    for ph, info in gate["phases"].items():
        periods[labels[ph]] = {
            "planned": [info.get("planned_first"), info.get("planned_last")],
            "days_counted": info["days"],
            "results": {name_of(c): {"present": v["present"], "days_with_L_at_or_above_theta": v["days_over"]}
                        for c, v in info["criteria"].items()},
            "episode_likely": info["episode"],
        }
    metrics_used = {k for c in configured for k in (cfg.criteria.get(c) or {})}
    days = []
    for d in tl["days"]:
        row: dict[str, Any] = {
            "date": d["date"], "weekday": d["weekday"],
            "period": labels.get(d["phase"], d["phase"]),
            "complete": d["complete"],
            "packets": d.get("packets_kept"),
            "L": {name_of(c): _r(d["L"].get(c)) for c in configured},
            "parts": {
                name_of(c): {metric_labels.get(k, k): {"value": _r(p.get("value")), "mu": _r(p.get("mu")), "w": p.get("w")}
                             for k, p in (d["parts"].get(c) or {}).items()}
                for c in configured
            },
        }
        days.append(row)
    baseline = {metric_labels.get(k, k): {"mean": _r(v["mean"]), "sd": _r(v["sd"]), "n": v["n"]}
                for k, v in tl.get("baseline_stats", {}).items() if k in metrics_used}
    ctx: dict[str, Any] = {
        "who": "the person you are talking with" if person_view else tl["persona"]["name"],
        "source": "scripted test run" if tl["profile"].get("has_plan") else "live home traffic",
        "areas" if person_view else "criteria": [name_of(c) for c in configured],
        "gate": {"theta": gate["params"]["theta"], "N": gate["params"]["N"], "M": gate["params"]["M"]},
        "periods": periods,
        "baseline_mean_sd_of_metrics": baseline,
        "days": days,
        "metric_scoring": {
            name_of(c): {metric_labels.get(k, k): {"w": s.get("w"), **{x: s.get("mf", {}).get(x) for x in ("type", "lo", "mid", "hi", "invert")}}
                         for k, s in (cfg.criteria.get(c) or {}).items()}
            for c in configured
        },
    }
    obs = tl.get("observed")
    if obs:
        # Layer 1: observed behaviour in real units and the risk flags the overview shows. For the
        # person, the timeline is already redacted (no crisis or self-harm sites).
        def clock(m):
            return None if m is None else f"{int(m // 60) % 24:02d}:{int(m % 60):02d}"
        ctx["observed_behaviour"] = {
            "note": ("what the network saw, before any model: quiet window at night (devices went quiet / "
                     "came back online; asleep, away or off look the same), hours in use, minutes in use "
                     "00:00-06:00, chat sessions, different sites. 'usual' = mean and SD over the baseline "
                     "days. A flag names a risk over the recent days, not a single day."),
            "usual": {k: {"mean": _r(v["mean"]), "sd": _r(v["sd"])} for k, v in obs.get("usual", {}).items()},
            "flags": [{"title": f["title"], "compared_with": "healthy people" if f.get("basis") == "reference" else "own usual weeks",
                       "days": f["days"], "count": f["count"], "of_last": f["window"],
                       **({"what": f.get("names")} if f.get("names") else {})} for f in obs.get("flags", [])],
            **({"healthy_reference": {
                "note": ("pooled healthy days of other people (scripted personas' baseline weeks = healthy "
                         "everyday profiles, or healthy volunteers); small and mixed lifestyles, so a "
                         "difference can reflect lifestyle rather than health"),
                "people": obs["reference"]["people"], "days": obs["reference"]["n_days"],
                "mean_sd": {k: {"mean": _r(v["mean"]), "sd": _r(v["sd"])} for k, v in obs["reference"]["stats"].items()},
            }} if obs.get("reference") else {}),
            "days": {
                d["date"]: {
                    "went_quiet": clock(o.get("quiet_start")), "back_online": clock(o.get("quiet_end")),
                    "quiet_hours": _r(o.get("quiet_hours"), 2), "hours_in_use": _r(o.get("online_hours"), 2),
                    "minutes_in_use_at_night": o.get("night_minutes"), "chat_sessions": o.get("chat_sessions"),
                    "different_sites": o.get("sites"),
                }
                for d in tl["days"] if (o := d.get("observed"))
            },
        }
    care = tl.get("care") or {}
    if care.get("routine"):
        r = care["routine"]
        ctx["routine_stated_by_the_person"] = {
            "week": r.get("week"), "away_from": r.get("away_from"), "away_to": r.get("away_to"),
            "bedtime": r.get("bedtime"), "wake": r.get("wake"), "bedtime_free_days": r.get("bedtime_free"),
            "wake_free_days": r.get("wake_free"), "devices": [d["name"] for d in r.get("devices", [])],
            "note": r.get("note"),
            "how_it_is_used": "usual ranges are learned per day type (away, home, free) once there are 5 baseline days of a type",
        }
    if care.get("away_periods"):
        ctx["away_periods"] = [{"from": p["from"], "to": p["to"], "reason": p.get("reason")} for p in care["away_periods"]]
    if not person_view and care.get("clinical"):
        c = care["clinical"]
        ctx["care_plan_by_clinicians"] = {
            "history": c.get("history"), "concerns": c.get("concerns"), "treatment": c.get("treatment"),
            "criteria_in_focus": c.get("criteria"), "risk_settings": c.get("focus"),
            "normal_ranges_set_by_clinician": c.get("normals"),
        }
    if not person_view:
        from .observability import OBSERVABILITY
        ctx["what_the_network_can_tell_per_criterion"] = {
            k: {"level": v["level"], "observes": v["observes"], "cannot": v["cannot"]} for k, v in OBSERVABILITY.items()}
    if not person_view and tl.get("notes"):
        ctx["notes_by_clinicians_and_parents"] = [{"date": n["date"], "text": n["text"]} for n in tl["notes"]]
    if not person_view:
        # Criteria without weights in the config: raw values only (no likelihood, outside the gate).
        # Never sent for the person (C9 is suicidality).
        unscored = [c for c in fasl.CRIT_KEYS if not cfg.configured(c)]
        per_day = {}
        for d in tl["days"]:
            vals = {metric_labels.get(k, k): _r(v) for k, v in d["metrics"].items()
                    if k[:2] in unscored and k[2] == "_" and isinstance(v, (int, float)) and not isinstance(v, bool) and v}
            if vals:
                per_day[d["date"]] = vals
        ctx["unscored_criteria"] = {
            "note": ("metrics of criteria the configuration does not score (no weights): raw daily values, "
                     "non-zero ones only; not part of any likelihood or the gate. For C9 (suicidality) the "
                     "portal flags a day when a metric is above its baseline mean + 2 SD, except "
                     "'Self-harm forum visits': without URLs in the gateway data it counts all reddit.com "
                     "packets, so it says nothing about self-harm sites and is never a C9 signal."),
            "criteria": [f"{c} {fasl.CRIT_NAMES[c]}" for c in unscored],
            "baseline_mean_sd": {metric_labels.get(k, k): {"mean": _r(v["mean"]), "sd": _r(v["sd"])}
                                 for k, v in tl.get("baseline_stats", {}).items() if k[:2] in unscored and k[2] == "_"},
            "days": per_day,
        }
    if not person_view and tl["persona"].get("expected"):
        ctx["scripted_expectations"] = {
            "note": ("expected outcomes of the test script (profile §9) for the CLINICAL phase only, not "
                     "observations. In the baseline phase every criterion is expected to be absent, so a "
                     "criterion present in the baseline is a false positive, never a match."),
            "criteria": {f"{c} {fasl.CRIT_NAMES[c]}": v for c, v in tl["persona"]["expected"].items()},
            "episode": tl["persona"].get("episode"),
        }
    return ctx


def system_blocks(ctx: dict[str, Any], person_view: bool) -> list[dict[str, Any]]:
    """Frozen instructions first, then the data (cached; questions vary after it)."""
    data = json.dumps(ctx, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return [
        {"type": "text", "text": SYSTEM_COMMON + (SYSTEM_PERSON if person_view else SYSTEM_CLINICIAN)},
        {"type": "text", "text": f"<results>\n{data}\n</results>", "cache_control": {"type": "ephemeral"}},
    ]


def clean_messages(messages: Iterable[dict[str, Any]], focus: str | None) -> list[dict[str, Any]]:
    """User/assistant text turns only, last MAX_TURNS, starting with a user turn."""
    out = [{"role": m["role"], "content": str(m["content"])[:4000]}
           for m in messages if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()]
    out = out[-MAX_TURNS:]
    while out and out[0]["role"] != "user":
        out.pop(0)
    if not out or out[-1]["role"] != "user":
        raise ValueError("the last message must be a question")
    if focus:
        out[-1] = {"role": "user", "content": f"(The screen currently shows: {focus})\n\n{out[-1]['content']}"}
    return out


def stream_answer(cfg: dict[str, Any], system: list[dict[str, Any]], messages: list[dict[str, Any]],
                  anthropic_client: Any = None) -> Iterator[str]:
    """Text chunks of Claude's answer."""
    if anthropic_client is None:
        import anthropic
        anthropic_client = anthropic.Anthropic(api_key=cfg["api_key"]) if cfg["api_key"] else anthropic.Anthropic()
    yield from stream_claude(anthropic_client, cfg["model"], system, messages)


def stream_claude(client: Any, model: str, system: list[dict[str, Any]],
                  messages: list[dict[str, Any]]) -> Iterator[str]:
    """Text chunks of Claude's answer. Refusals and errors end with a short note instead of raising."""
    import anthropic
    try:
        with client.beta.messages.stream(
            model=model,
            max_tokens=16000,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            for text in stream.text_stream:
                yield text
            final = stream.get_final_message()
        if final.stop_reason == "refusal":
            yield "\n\n(The assistant could not answer this question.)"
        elif final.stop_reason == "max_tokens":
            yield "\n\n(The answer was cut off.)"
    except anthropic.AuthenticationError:
        yield "(The assistant is not set up: no valid Anthropic credentials on the server.)"
    except anthropic.RateLimitError:
        yield "(The assistant is busy. Please try again in a minute.)"
    except anthropic.APIStatusError as e:
        yield f"(The assistant failed: {e.status_code}.)"
    except anthropic.APIConnectionError:
        yield "(The assistant could not reach the Anthropic API.)"
