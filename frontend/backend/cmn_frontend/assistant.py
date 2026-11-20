"""Explanation assistant: answers questions about one profile's computed results, in natural language.

It is an explanation layer only. Claude receives the derived daily results that the portal already
shows (likelihoods per criterion, metric values, membership degrees μ and weights w, baseline mean
and SD, the gate per period) and explains where a finding comes from. It never sees raw packets,
IP addresses, hostnames or device names, and it must not diagnose.

Off by default, because questions and these derived results are sent to a model. A multi-profile
user turns it on in the portal (Settings → Assistant) and chooses the provider: Anthropic (Claude,
with the project's Claude key) or a local model behind an OpenAI-compatible endpoint (Ollama,
llama.cpp server, LM Studio; see llm.py), so nothing leaves the team's own machines. Provider, model,
endpoint and key are stored in <home>/assistant.json (readable by the owner only; the key is never
sent back to a browser). Environment variables give the defaults:

    CMN_ASSISTANT=1                         # on
    CMN_ASSISTANT_PROVIDER=anthropic        # or local
    CMN_ASSISTANT_MODEL=claude-sonnet-5-5   # model of that provider
    ANTHROPIC_API_KEY=...
    CMN_LOCAL_URL=http://127.0.0.1:11434/v1 # local: OpenAI-compatible base URL
    CMN_LOCAL_API_KEY=...                   # local: only if the server wants one

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

from . import fasl, llm
from .llm import DEFAULT_PROVIDER, PROVIDERS
from .settings import PRODUCT_NAME, PRODUCT_SUBTITLE
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
    """Assistant settings: <home>/assistant.json over environment defaults."""

    def __init__(self, home: Path):
        self.path = Path(home) / "assistant.json"

    def _file(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _env_provider() -> str:
        p = os.environ.get("CMN_ASSISTANT_PROVIDER", "").strip().lower()
        return p if p in PROVIDERS else DEFAULT_PROVIDER

    def load(self) -> dict[str, Any]:
        f = self._file()
        env_provider = self._env_provider()
        provider = f.get("provider") if f.get("provider") in PROVIDERS else env_provider
        p = PROVIDERS[provider]
        env_on = os.environ.get("CMN_ASSISTANT", "").lower() in ("1", "true", "yes")
        key = (f.get("api_keys") or {}).get(provider) or os.environ.get(p["key_env"], "")
        env_model = os.environ.get("CMN_ASSISTANT_MODEL") if provider == env_provider else None
        model = (f.get("models") or {}).get(provider) or env_model or p["default_model"]
        out = {"enabled": bool(f.get("enabled", env_on)), "provider": provider, "model": model, "api_key": key}
        if provider == "local":
            out["base_url"] = (f.get("base_urls") or {}).get("local") or os.environ.get("CMN_LOCAL_URL") \
                or p["default_base_url"]
        return out

    def public(self) -> dict[str, Any]:
        c = self.load()
        p = PROVIDERS[c["provider"]]
        local = c["provider"] == "local"
        f = self._file()
        base_url = (f.get("base_urls") or {}).get("local") or os.environ.get("CMN_LOCAL_URL") \
            or PROVIDERS["local"]["default_base_url"]
        if local:
            notice = (f"Your question and this profile's daily results (no raw traffic, addresses or device names) "
                      f"are sent to a model running on the team's own computer ({c['model']}); nothing goes to "
                      f"an outside company.")
        else:
            notice = (f"Your question and this profile's daily results (no raw traffic, addresses or device "
                      f"names) are sent to Anthropic's Claude ({c['model']}) to write the answer.")
        return {"enabled": c["enabled"], "provider": c["provider"], "model": c["model"],
                "default_model": p["default_model"],
                "has_key": True if local else (bool(c["api_key"]) or _anthropic_profile()),
                "has_claude_key": bool((f.get("api_keys") or {}).get("anthropic")),   # stored in the file
                "base_url": llm.public_base_url(base_url),
                "providers": [{"id": k, "label": v["label"], "default_model": v["default_model"],
                               **({"default_base_url": v["default_base_url"]} if "default_base_url" in v else {})}
                              for k, v in PROVIDERS.items()],
                "notice": notice}

    def save(self, enabled: bool, model: str, api_key: str | None, provider: str | None = None,
             base_url: str | None = None) -> None:
        """api_key None: keep the stored key of that provider; "": remove it. provider None: keep the
        current one. Models, keys and the endpoint are kept per provider; unknown providers are dropped."""
        model = model.strip()
        if not model or len(model) > 200:
            raise ValueError("model is required")
        f = self._file()
        provider = provider or (f.get("provider") if f.get("provider") in PROVIDERS else self._env_provider())
        if provider not in PROVIDERS:
            raise ValueError(f"unknown provider {provider!r}")
        keys = {k: v for k, v in (f.get("api_keys") or {}).items() if k in PROVIDERS}
        models = {k: v for k, v in (f.get("models") or {}).items() if k in PROVIDERS}
        urls = {k: v for k, v in (f.get("base_urls") or {}).items() if k in PROVIDERS}
        models[provider] = model
        if api_key is not None:
            if api_key.strip():
                keys[provider] = api_key.strip()
            else:
                keys.pop(provider, None)
        if base_url is not None and provider == "local":
            if base_url.strip():
                urls["local"] = llm.check_base_url(base_url)
            else:
                urls.pop("local", None)
        f = {"enabled": bool(enabled), "provider": provider, "models": models, "api_keys": keys,
             **({"base_urls": urls} if urls else {})}
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


PERSON_MAX_WORDS = 80          # person replies, unless they ask for more detail
CLINICIAN_MAX_WORDS = 150      # clinician replies, unless they ask for more detail

# The UI's answer controls (B2) send these as the next user message. clean_messages() turns them into
# an explicit instruction, so the model rewrites its previous answer instead of answering "Shorter".
CONTROL_MESSAGES = {
    "shorter": ("[Shorter] Rewrite your previous answer shorter: at most 2 sentences, the same facts, "
                "nothing new."),
    "more detail": ("[More detail] Expand your previous answer: add the days, values and comparisons from "
                    "<results> behind it. Stay on the same question; nothing that is not in <results>."),
}
CONTROL_ALIASES = {"-": "shorter", "−": "shorter", "+": "more detail", "more details": "more detail",
                   "shorter please": "shorter", "more detail please": "more detail"}

SYSTEM_COMMON = f"""\
You are the explanation assistant of {PRODUCT_NAME} ({PRODUCT_SUBTITLE}), a research prototype. It derives
daily metrics from a home router's network traffic metadata (packet timing, volume, DNS lookups; no
content) and turns them into likelihoods L between 0 and 1 for DSM-5 depression criteria with a fuzzy
scoring model (FASL): each metric value is mapped to a membership degree μ between 0 and 1 and weighted
with w; L = Σ w·μ, clipped to [0, 1]. A criterion counts as "present" in a period when L ≥ θ on at
least N of the period's last M days. The data you get is in <results>.

Your only job is to explain these results: what a value means, which metrics drove a likelihood on a
day, how a period compares with the usual weeks, and how the scoring works. Rules:
- Answer the question first, in 1–3 sentences. Where it fits, answer from <results> "week_overview"
  (the last 7 days: went quiet, back online, time in use, compared with the usual weeks); go into
  likelihoods, metrics and scoring only when the question is about them.
- Be brief: group days that look alike ("Mon to Wed", "the weekend") instead of one line per day,
  give only the values that answer the question, and stop once it is answered. No summary or closing
  line that repeats the answer.
- Use only numbers that appear in <results> (rounding is fine). Do not compute new figures such as
  differences or averages; say a difference in words ("about an hour later", "clearly less"). Name the
  day and the value you rely on. If the data does not answer a question, say so in one sentence. Never
  invent values.
- Do not diagnose, do not predict a condition, and do not recommend treatment.
- Do not add an unrequested part on what the data can or cannot imply, caveats or disclaimers; the
  portal explains its limits elsewhere. Answer only what was asked.
- "typical" refers to the reference group (other people's usual weeks); use that word for it.
- Say "devices quiet at night" or "went quiet", not "sleep", for the quiet window: the network cannot
  tell asleep from away or switched off.
- No tables or headings unless asked. Basic Markdown (bold, bullet lists) is rendered.
- Answer controls: a message starting with [Shorter] asks you to rewrite your previous answer shorter
  (at most 2 sentences, same facts); one starting with [More detail] asks you to expand your previous
  answer with the days and values from <results> behind it. In both cases add no new topic and nothing
  that is not in <results>. If there is no previous answer, ask what they would like to know.
- The data covers scripted test personas or consenting participants; still treat it as personal.
"""

SYSTEM_PERSON = f"""\
You are talking with the person whose data this is. Write in plain, warm, everyday language.
- Keep every reply to about {PERSON_MAX_WORDS} words at most, unless the person asks for more detail
  ([More detail], "explain more", "in detail"). Usually 2–4 sentences; at most 3 short bullets.
- Describe only what was observed: when the devices went quiet and came back online, how long they
  were in use, use at night, chats and different sites, and how that compares with the person's usual
  weeks (more or less, earlier or later). Use the everyday area names in <results>. Do not use
  DSM-5 criterion names, criterion numbers, diagnoses or clinical terms.
- Never give reasons, meanings, feelings, symptoms, conditions or diagnoses, and never guess why
  something changed or what it says about the person's health, also not when they ask again, insist
  or rephrase. Do not repeat clinical words the person uses (for example "depressed", "insomnia",
  "anxiety"). Say briefly that the data shows when devices were used, not why, and suggest talking
  about it with their care team.
- Do not tell the person which changes were expected or planned; you do not know that, and it must not
  influence them.
- Do not quote the 0–1 area scores, thresholds, weights or rules like "N of M days", and avoid notation
  (θ, μ, L), unless the person explicitly asks how the scoring works. Say in words how different a day
  was ("a little", "clearly"), and describe what happened in everyday terms ("your devices went quiet
  later than usual", "fewer different websites than usual"), with a value only when it helps.
- If the person says they feel unwell, are worried, or mentions self-harm, respond with care, encourage
  them to talk to their care team, someone they trust or a professional, and, for urgent danger,
  mention emergency help (in Switzerland: 144, or Die Dargebotene Hand at 143).
"""

SYSTEM_CLINICIAN = f"""\
You are talking with a clinician, researcher or carer who supervises this person. You may use the
DSM-5 criterion names, the scoring notation and the numbers directly.
- Answer first in 1–3 sentences, then at most 4 short bullet points with the days and values behind
  it. Keep it under about {CLINICIAN_MAX_WORDS} words unless they ask for more detail.
- Where <results> contains expected outcomes of a scripted persona, you may compare observed with
  expected, but make clear that the expectations come from the test script, not from the data.
- Network patterns can change for ordinary reasons (travel, holidays, a new device, guests); mention
  one only where the routine, away periods or notes in <results> point to it.
- A criterion being present or an episode flag is a screening signal of this prototype, not a
  diagnosis; say so only if the question asks for a diagnosis.
"""


def _clock(m: Any) -> str | None:
    """Minutes from midnight (negative = the evening before) as HH:MM."""
    if not isinstance(m, (int, float)) or isinstance(m, bool) or not math.isfinite(m):
        return None
    m = int(round(m))
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"


def typical_wording(text: str) -> str:
    """D1: "healthy people" -> "typical" in flag texts that still use the old wording."""
    for old, new in (("than healthy people usually do", "than is typical"), ("than healthy people", "than typical"),
                     ("healthy people", "typical"), ("healthy reference", "typical range"),
                     ("Healthy people", "Typical")):
        text = text.replace(old, new)
    return text


# Week overview (A4/B1): the tracks of the person's week table, in display units.
WEEK_TRACKS = [("went_quiet", "quiet_start", "clock"), ("back_online", "quiet_end", "clock"),
               ("quiet_hours", "quiet_hours", "h"), ("hours_in_use", "online_hours", "h"),
               ("minutes_in_use_at_night", "night_minutes", "min")]
WEEK_TRACKS_CLINICIAN = [("chat_sessions", "chat_sessions", "count"), ("different_sites", "sites", "count")]
# Words for the deviation from the usual weeks (z in SD), per track direction.
DIRECTION_WORDS = {"quiet_start": ("later", "earlier"), "quiet_end": ("later", "earlier"),
                   "quiet_hours": ("longer", "shorter"), "online_hours": ("more", "less"),
                   "night_minutes": ("more", "less"), "chat_sessions": ("more", "fewer"), "sites": ("more", "fewer")}


def compare_word(track: str, z: Any) -> str | None:
    """The deviation in words: "as usual", "a little later", "clearly later" (thresholds 1 and 1.5 SD)."""
    if not isinstance(z, (int, float)) or isinstance(z, bool) or not math.isfinite(z):
        return None
    if abs(z) < 1.0:
        return "as usual"
    up, down = DIRECTION_WORDS.get(track, ("higher", "lower"))
    return f"{'clearly' if abs(z) >= 1.5 else 'a little'} {up if z > 0 else down}"


def _show(track_unit: str, v: Any) -> Any:
    if track_unit == "clock":
        return _clock(v)
    if track_unit == "h":
        return _r(v, 1)
    return None if v is None else (int(round(v)) if isinstance(v, (int, float)) and math.isfinite(v) else v)


def _usual_display(key: str, unit: str, s: dict[str, Any] | None) -> dict[str, Any] | None:
    if not s:
        return None
    if unit == "clock":
        return {"mean": _clock(s.get("mean")), "sd_minutes": _show("min", s.get("sd"))}
    return {"mean": _show(unit, s.get("mean")), "sd": _show(unit, s.get("sd"))}


def week_overview(days: list[dict[str, Any]], obs: dict[str, Any], person_view: bool) -> dict[str, Any]:
    """The last 7 days with data, as in the person's week table, with the usual weeks in the same units."""
    tracks = WEEK_TRACKS + ([] if person_view else WEEK_TRACKS_CLINICIAN)
    rows = []
    for d in [d for d in days if (d.get("observed") or {}).get("has_data")][-7:]:
        o = d["observed"]
        row: dict[str, Any] = {"date": d["date"], "weekday": d.get("weekday")}
        if o.get("day_type"):
            row["day_type"] = o["day_type"]
        compared = {}
        for name, key, unit in tracks:
            row[name] = _show(unit, o.get(key))
            w = compare_word(key, (o.get("deviation") or {}).get(key))
            if w:
                compared[name] = w
        row["compared_with_usual_weeks"] = compared
        if not person_view and o.get("percentile_ref"):
            row["percentile_vs_typical"] = {k: _r(v, 0) for k, v in o["percentile_ref"].items()}
        rows.append(row)
    usual = obs.get("usual") or {}
    return {
        "note": ("the last 7 days with data (as in the week table); 'compared_with_usual_weeks': as usual "
                 "(within 1 SD of the usual weeks), a little (1-1.5 SD) or clearly (beyond 1.5 SD) different; "
                 "went quiet / back online = devices quiet at night (asleep, away or off look the same)"),
        "days": rows,
        "usual_weeks": {name: u for name, key, unit in tracks if (u := _usual_display(key, unit, usual.get(key)))},
    }


def _flag(f: dict[str, Any]) -> dict[str, Any]:
    out = {"title": typical_wording(f["title"]),
           "compared_with": "typical range (other people's usual weeks)" if f.get("basis") == "reference"
           else "own usual weeks",
           "days": f["days"], "count": f["count"], "of_last": f["window"]}
    if f.get("kind") == "change":
        out["kind"] = "notable change in the improving direction, to discuss (not a risk)"
    if f.get("names"):
        out["what"] = f["names"]
    return out


CLOCK_TRACKS = ("quiet_start", "quiet_end")      # minutes from midnight, also given as HH:MM


def _typical_reference(ref: dict[str, Any]) -> dict[str, Any]:
    """The typical range: K1's percentile shape (tracks p16/p50/p84) or the v2 pooled mean/SD.

    Went quiet / back online also as clock times, so the model never converts minutes itself."""
    if ref.get("tracks"):
        clock = {k: {p: _clock(v.get(p)) for p in ("p16", "p50", "p84")}
                 for k, v in ref["tracks"].items() if k in CLOCK_TRACKS}
        return {"label": typical_wording(ref.get("label") or "typical"), "source": ref.get("source"),
                **({"clock_times": clock} if clock else {}),
                "percentiles_16_50_84": {
                    k: {"p16": _r(v.get("p16"), 2), "p50": _r(v.get("p50"), 2), "p84": _r(v.get("p84"), 2),
                        **({"n": v["n"]} if v.get("n") else {}),
                        **({"citation": v["citation"]} if v.get("citation") else {}),
                        **({"proxy_note": v["proxy_note"]} if v.get("proxy_note") else {})}
                    for k, v in ref["tracks"].items()}}
    return {
        "note": ("pooled usual weeks of other people (scripted personas' baseline weeks, or volunteers); small "
                 "and mixed lifestyles, so a difference can reflect lifestyle"),
        "people": len(ref.get("people") or []), "days": ref.get("n_days"),
        "mean_sd": {k: {"mean": _r(v["mean"]), "sd": _r(v["sd"])} for k, v in (ref.get("stats") or {}).items()},
        "clock_times": {k: {"mean": _clock(v["mean"]), "sd_minutes": _show("min", v["sd"])}
                        for k, v in (ref.get("stats") or {}).items() if k in CLOCK_TRACKS},
    }


def observed_context(days: list[dict[str, Any]], obs: dict[str, Any], person_view: bool) -> dict[str, Any]:
    """Layer 1: observed behaviour in real units and the flags the overview shows (all days).

    For the person the timeline is already redacted (no crisis or self-harm sites, no typical range)."""
    out: dict[str, Any] = {
        "note": ("what the network saw, before any model: devices quiet at night (went quiet / back online; "
                 "asleep, away or off look the same), hours in use, minutes in use 00:00-06:00, chat sessions, "
                 "different sites. 'usual' = mean and SD over the baseline days (times as minutes from "
                 "midnight, negative = evening before). A flag names a pattern over the recent days, not a "
                 "single day."),
        "usual": {k: {"mean": _r(v["mean"]), "sd": _r(v["sd"]),
                      **({"mean_clock": _clock(v["mean"])} if k in CLOCK_TRACKS else {})}
                  for k, v in obs.get("usual", {}).items()},
        "flags": [_flag(f) for f in obs.get("flags", [])],
        "days": {
            d["date"]: {
                "went_quiet": _clock(o.get("quiet_start")), "back_online": _clock(o.get("quiet_end")),
                "quiet_hours": _r(o.get("quiet_hours"), 2), "hours_in_use": _r(o.get("online_hours"), 2),
                "minutes_in_use_at_night": o.get("night_minutes"), "chat_sessions": o.get("chat_sessions"),
                "different_sites": o.get("sites"),
                **({"went_quiet_sd_last_7_nights_min": _r(o["quiet_start_sd7"], 0)}
                   if o.get("quiet_start_sd7") is not None else {}),
            }
            for d in days if (o := d.get("observed"))
        },
    }
    if obs.get("reference") and not person_view:
        out["typical_reference"] = _typical_reference(obs["reference"])
    return out


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
        ctx["week_overview"] = week_overview(tl["days"], obs, person_view)
        ctx["observed_behaviour"] = observed_context(tl["days"], obs, person_view)
    care = tl.get("care") or {}
    if care.get("routine"):
        r = care["routine"]
        ctx["routine_stated_by_the_person"] = {
            "week": r.get("week"), "away_from": r.get("away_from"), "away_to": r.get("away_to"),
            "bedtime": r.get("bedtime"), "wake": r.get("wake"), "bedtime_free_days": r.get("bedtime_free"),
            "wake_free_days": r.get("wake_free"), "devices": [d["name"] for d in r.get("devices", [])],
            "note": r.get("note"),
            "how_it_is_used": ("week: per weekday the morning (am) and afternoon (pm); usual ranges are learned per "
                               "day type (away, home, free; a day with an away half counts as away, else with a home "
                               "half as home) once there are 5 baseline days of a type"),
        }
    if care.get("away_periods"):
        ctx["away_periods"] = [{"from": p["from"], "to": p["to"], "reason": p.get("reason")} for p in care["away_periods"]]
    if not person_view and care.get("clinical"):
        c = care["clinical"]
        ctx["care_plan_by_clinicians"] = {
            "purpose": c.get("purpose"),   # assessment (status vs. typical) or treatment monitoring (change)
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


def control_message(text: str) -> str | None:
    """The explicit instruction for an answer control ("Shorter" / "More detail"), else None."""
    key = " ".join(str(text).strip().strip(".!").lower().split())
    key = CONTROL_ALIASES.get(key, key)
    return CONTROL_MESSAGES.get(key)


def clean_messages(messages: Iterable[dict[str, Any]], focus: str | None) -> list[dict[str, Any]]:
    """User/assistant text turns only, last MAX_TURNS, starting with a user turn."""
    out = [{"role": m["role"], "content": str(m["content"])[:4000]}
           for m in messages if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()]
    out = out[-MAX_TURNS:]
    while out and out[0]["role"] != "user":
        out.pop(0)
    if not out or out[-1]["role"] != "user":
        raise ValueError("the last message must be a question")
    control = control_message(out[-1]["content"])
    if control:
        out[-1] = {"role": "user", "content": control}
        return out          # the controls rewrite the previous answer; the screen focus does not matter
    if focus:
        out[-1] = {"role": "user", "content": f"(The screen currently shows: {focus})\n\n{out[-1]['content']}"}
    return out


def stream_answer(cfg: dict[str, Any], system: list[dict[str, Any]], messages: list[dict[str, Any]],
                  client: Any = None, anthropic_client: Any = None) -> Iterator[str]:
    """Text chunks of the answer, from the configured provider (llm.py). anthropic_client: the v2 name
    of `client`, still accepted (eval/assistant_eval.py passes it)."""
    yield from llm.stream_text(cfg, system, messages, client if client is not None else anthropic_client)


def stream_claude(client: Any, model: str, system: list[dict[str, Any]],
                  messages: list[dict[str, Any]]) -> Iterator[str]:
    """Text chunks of Claude's answer (kept for callers of v2; see llm.stream_claude)."""
    yield from llm.stream_claude(client, model, system, messages)
