"""Explanation assistant: answers questions about one profile's computed results, in natural language.

It is an explanation layer only. Claude receives the derived daily results that the portal already
shows (likelihoods per criterion, metric values, membership degrees μ and weights w, baseline mean
and SD, the gate per period) and explains where a finding comes from. It never sees raw packets,
IP addresses, hostnames or device names, and it must not diagnose.

Off by default, because questions and these derived results are sent to an external model API.
A multi-profile user turns it on in the portal (Settings → Assistant): provider, model and API key are
stored in <home>/assistant.json (readable by the owner only; the key is never sent back to a
browser). Environment variables give the defaults:

    CMN_ASSISTANT=1                         # on
    CMN_ASSISTANT_PROVIDER=openrouter       # or anthropic
    CMN_ASSISTANT_MODEL=deepseek/deepseek-v4.1-flash-1017
    OPENROUTER_API_KEY=... / ANTHROPIC_API_KEY=...

Providers: "openrouter" (OpenRouter's chat completions API, any model it serves; used for testing)
and "anthropic" (Claude through the official SDK).

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
    "openrouter": {"label": "OpenRouter", "default_model": "deepseek/deepseek-v4.1-flash-1017",
                   "key_env": "OPENROUTER_API_KEY"},
    "anthropic": {"label": "Anthropic (Claude)", "default_model": "claude-opus-5-5",
                  "key_env": "ANTHROPIC_API_KEY"},
}
DEFAULT_PROVIDER = "openrouter"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
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


class AssistantConfig:
    """Assistant settings: <home>/assistant.json over environment defaults. Keys per provider."""

    def __init__(self, home: Path):
        self.path = Path(home) / "assistant.json"

    def _file(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def load(self) -> dict[str, Any]:
        f = self._file()
        provider = f.get("provider") or os.environ.get("CMN_ASSISTANT_PROVIDER", DEFAULT_PROVIDER)
        if provider not in PROVIDERS:
            provider = DEFAULT_PROVIDER
        env_on = os.environ.get("CMN_ASSISTANT", "").lower() in ("1", "true", "yes")
        keys = f.get("api_keys") or {}
        key = keys.get(provider) or os.environ.get(PROVIDERS[provider]["key_env"], "")
        model = (f.get("models") or {}).get(provider) or os.environ.get("CMN_ASSISTANT_MODEL") \
            or PROVIDERS[provider]["default_model"]
        return {"enabled": bool(f.get("enabled", env_on)), "provider": provider, "model": model,
                "api_key": key}

    def public(self) -> dict[str, Any]:
        c = self.load()
        return {"enabled": c["enabled"], "provider": c["provider"], "model": c["model"],
                "has_key": bool(c["api_key"]) or c["provider"] == "anthropic" and _anthropic_profile(),
                "providers": {k: {"label": v["label"], "default_model": v["default_model"]} for k, v in PROVIDERS.items()},
                "notice": (f"Your question and this profile's daily results (no raw traffic, addresses or device "
                           f"names) are sent to {PROVIDERS[c['provider']]['label']} ({c['model']}) to write the answer.")}

    def save(self, enabled: bool, provider: str, model: str, api_key: str | None) -> None:
        """api_key None: keep the stored key; "": remove it."""
        if provider not in PROVIDERS:
            raise ValueError(f"provider must be one of {', '.join(PROVIDERS)}")
        model = model.strip()
        if not model or len(model) > 200:
            raise ValueError("model is required")
        f = self._file()
        f.update({"enabled": bool(enabled), "provider": provider})
        f.setdefault("models", {})[provider] = model
        keys = f.setdefault("api_keys", {})
        if api_key is not None:
            if api_key.strip():
                keys[provider] = api_key.strip()
            else:
                keys.pop(provider, None)
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
- Keep answers short: a few sentences or a short list. No tables unless asked.
- The data covers scripted test personas or consenting participants; still treat it as personal.
"""

SYSTEM_PERSON = """\
You are talking with the person whose data this is. Write in plain, warm, everyday language.
- Use the everyday area names given in <results> (for example "Sleep", "Daily rhythm"). Do not use
  DSM-5 criterion names, criterion numbers, diagnoses or clinical terms, and do not speculate about
  what a pattern could mean medically.
- Do not tell the person which changes were expected or planned; you do not know that, and it must not
  influence them.
- Avoid technical notation (θ, μ, L) unless the person asks how the scoring works.
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
    if not person_view and tl["persona"].get("expected"):
        ctx["scripted_expectations"] = {
            "note": "expected outcomes of the test script (profile §9), not observations",
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
                  anthropic_client: Any = None, http_client: Any = None) -> Iterator[str]:
    """Text chunks of the answer from the configured provider."""
    if cfg["provider"] == "openrouter":
        if not cfg["api_key"]:
            yield "(The assistant is not set up: no OpenRouter API key. Add it under Settings → Assistant.)"
            return
        yield from stream_openrouter(cfg["api_key"], cfg["model"], system, messages, http_client)
        return
    if anthropic_client is None:
        import anthropic
        anthropic_client = anthropic.Anthropic(api_key=cfg["api_key"]) if cfg["api_key"] else anthropic.Anthropic()
    yield from stream_claude(anthropic_client, cfg["model"], system, messages)


def stream_openrouter(api_key: str, model: str, system: list[dict[str, Any]],
                      messages: list[dict[str, Any]], http_client: Any = None) -> Iterator[str]:
    """OpenRouter chat completions with server-sent events; errors end with a short note."""
    import httpx
    body = {
        "model": model,
        "stream": True,
        "messages": [{"role": "system", "content": "\n\n".join(b["text"] for b in system)}] + messages,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    client = http_client or httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))
    try:
        with client.stream("POST", OPENROUTER_URL, json=body, headers=headers) as r:
            if r.status_code != 200:
                r.read()
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except ValueError:
                    msg = ""
                yield {401: "(The assistant is not set up: the OpenRouter API key was rejected.)",
                       402: "(The OpenRouter account has no credit left.)",
                       429: "(The assistant is busy. Please try again in a minute.)"}.get(
                    r.status_code, f"(The assistant failed: {r.status_code} {msg})".strip())
                return
            finish = None
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue                       # keep-alive comments
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ev = json.loads(data)
                except ValueError:
                    continue
                if ev.get("error"):
                    yield f"\n\n(The assistant failed: {ev['error'].get('message', 'error')})"
                    return
                for ch in ev.get("choices") or []:
                    text = (ch.get("delta") or {}).get("content")
                    if text:
                        yield text
                    finish = ch.get("finish_reason") or finish
            if finish == "length":
                yield "\n\n(The answer was cut off.)"
    except httpx.HTTPError:
        yield "(The assistant could not reach OpenRouter.)"
    finally:
        if http_client is None:
            client.close()


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
