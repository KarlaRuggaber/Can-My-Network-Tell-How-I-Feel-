"""Provider layer of the assistant: the same two calls for Anthropic and for a local model.

- ``stream_text(cfg, system, messages)``: text chunks of an answer (explanation assistant).
- ``complete_json(cfg, system, user, schema)``: one answer as a dict that follows a JSON schema
  (routine and focus suggestions).

Providers (``cfg["provider"]``):

- ``anthropic``: Claude through the official SDK, as in v2 (adaptive thinking, structured output).
- ``local``: any OpenAI-compatible endpoint (``POST {base_url}/chat/completions``): Ollama
  (``http://127.0.0.1:11434/v1``), a llama.cpp server (``http://127.0.0.1:8080/v1``) or LM Studio
  (``http://127.0.0.1:1234/v1``). Text is streamed as server-sent events. JSON output uses
  ``response_format: json_schema``, which these servers turn into a grammar, so the model can only
  produce text that parses against the schema; a server that does not know json_schema gets
  ``json_object`` (JSON mode) with the schema in the system prompt instead. Nothing leaves the
  machine that runs the model.

``cfg`` is what ``assistant.AssistantConfig.load()`` returns: provider, model, api_key and, for
``local``, base_url. Errors never raise out of ``stream_text`` (the answer ends with a short note
instead); ``complete_json`` raises ``LLMError`` (a ``ValueError``) with a short, user-facing reason.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable, Iterator

PROVIDERS: dict[str, dict[str, Any]] = {
    "anthropic": {"label": "Anthropic (Claude)", "default_model": "claude-sonnet-5-5",
                  "key_env": "ANTHROPIC_API_KEY"},
    "local": {"label": "Local model (OpenAI-compatible endpoint)", "default_model": "qwen3.8:27b-mlx",
              "default_base_url": "http://127.0.0.1:11434/v1", "key_env": "CMN_LOCAL_API_KEY"},
}
DEFAULT_PROVIDER = "anthropic"

LOCAL_TIMEOUT = 600.0          # a 3B model on a laptop CPU/GPU reads a long <results> block slowly
LOCAL_MAX_TOKENS = 4000        # answers are short (K2's prompt rules); room for a thinking model
LOCAL_JSON_MAX_TOKENS = 6000


def _extra_body() -> dict[str, Any]:
    """CMN_LOCAL_EXTRA_BODY: JSON merged into every local request, e.g. {"reasoning_effort": "none"}
    to switch off a model's thinking, or {"temperature": 0.2}."""
    raw = os.environ.get("CMN_LOCAL_EXTRA_BODY", "").strip()
    if not raw:
        return {}
    try:
        out = json.loads(raw)
    except ValueError:
        raise LLMError("CMN_LOCAL_EXTRA_BODY is not valid JSON")
    return out if isinstance(out, dict) else {}


class LLMError(ValueError):
    """A short reason the model gave no usable answer (shown to the user)."""


# ---- shared helpers ----

def system_text(system: str | Iterable[dict[str, Any]]) -> str:
    """Anthropic system blocks (with cache_control) as one plain system prompt."""
    if isinstance(system, str):
        return system
    return "\n\n".join(b["text"] for b in system if b.get("type", "text") == "text")


def parse_json(text: str) -> dict[str, Any]:
    """The JSON object in a model's answer (small models sometimes wrap it in ``` fences)."""
    text = text.strip()
    try:
        out = json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LLMError("the assistant gave no JSON")
        try:
            out = json.loads(m.group(0))
        except ValueError:
            raise LLMError("the assistant gave invalid JSON")
    if not isinstance(out, dict):
        raise LLMError("the assistant gave no JSON object")
    return out


def public_base_url(url: str) -> str:
    """The endpoint without credentials, for the settings page."""
    return re.sub(r"//[^/@]*@", "//", url)


def check_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+(/\S*)?$", url) or len(url) > 300:
        raise ValueError("the endpoint must be an http(s) URL, e.g. http://127.0.0.1:11434/v1")
    return url


# ---- entry points ----

def check_local(base_url: str, model: str, api_key: str = "", client: Any = None) -> dict[str, Any]:
    """Can the portal reach the endpoint, and does it serve this model? ({ok, message, models})."""
    import httpx
    cfg = {"base_url": base_url, "model": model, "api_key": api_key}
    http = _local_client(cfg, client)
    try:
        r = http.get(f"{base_url.rstrip('/')}/models", timeout=10.0)
        r.raise_for_status()
        models = sorted(str(m.get("id")) for m in (r.json().get("data") or []) if m.get("id"))
    except httpx.HTTPError as e:
        msg = _local_error(e, cfg)
        return {"ok": False, "message": f"{msg[0].upper()}{msg[1:]}.", "models": []}
    except ValueError:
        return {"ok": False, "message": "The endpoint answered, but not like an OpenAI-compatible server.",
                "models": []}
    finally:
        if client is None:
            http.close()
    if model in models:
        return {"ok": True, "message": f"Reached the endpoint; it serves {model}.", "models": models}
    listed = ", ".join(models[:8]) or "none"
    return {"ok": False, "models": models,
            "message": f"Reached the endpoint, but it has no model \"{model}\" (available: {listed})."}


def stream_text(cfg: dict[str, Any], system: str | list[dict[str, Any]], messages: list[dict[str, Any]],
                client: Any = None) -> Iterator[str]:
    """Text chunks of the answer. Refusals and errors end with a short note instead of raising."""
    if cfg.get("provider", DEFAULT_PROVIDER) == "local":
        yield from _local_stream(cfg, system_text(system), messages, client)
    else:
        if client is None:
            client = _anthropic_client(cfg)
        yield from stream_claude(client, cfg["model"], system, messages)


def complete_json(cfg: dict[str, Any], system: str, user: str, schema: dict[str, Any],
                  client: Any = None) -> dict[str, Any]:
    """One answer that follows ``schema`` (raises LLMError with a short reason)."""
    if cfg.get("provider", DEFAULT_PROVIDER) == "local":
        return _local_json(cfg, system, user, schema, client)
    return _claude_json(cfg, system, user, schema, client)


# ---- Anthropic ----

def _anthropic_client(cfg: dict[str, Any]) -> Any:
    import anthropic
    return anthropic.Anthropic(api_key=cfg["api_key"]) if cfg.get("api_key") else anthropic.Anthropic()


def stream_claude(client: Any, model: str, system: str | list[dict[str, Any]],
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


def _claude_json(cfg: dict[str, Any], system: str, user: str, schema: dict[str, Any],
                 client: Any = None) -> dict[str, Any]:
    import anthropic
    if client is None:
        client = _anthropic_client(cfg)
    try:
        msg = client.beta.messages.create(
            model=cfg["model"], max_tokens=8000, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}, "effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
    except anthropic.AuthenticationError:
        raise LLMError("no valid Anthropic credentials (Settings → Assistant)")
    except anthropic.RateLimitError:
        raise LLMError("the assistant is busy, try again in a minute")
    except anthropic.APIStatusError as e:
        raise LLMError(f"the assistant failed ({e.status_code})")
    except anthropic.APIConnectionError:
        raise LLMError("could not reach the Anthropic API")
    if msg.stop_reason == "refusal":
        raise LLMError("the assistant could not answer this")
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return json.loads(text)


# ---- local, OpenAI-compatible ----

def _local_client(cfg: dict[str, Any], client: Any) -> Any:
    if client is not None:
        return client
    import httpx
    headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg.get("api_key") else {}
    return httpx.Client(timeout=httpx.Timeout(LOCAL_TIMEOUT, connect=10.0), headers=headers)


def _local_url(cfg: dict[str, Any]) -> str:
    base = (cfg.get("base_url") or PROVIDERS["local"]["default_base_url"]).rstrip("/")
    return f"{base}/chat/completions"


def _local_error(e: Exception, cfg: dict[str, Any]) -> str:
    import httpx
    where = public_base_url(cfg.get("base_url") or PROVIDERS["local"]["default_base_url"])
    if isinstance(e, httpx.TimeoutException):
        return f"the local model at {where} took too long to answer"
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 404:
            return f"the local endpoint has no model \"{cfg['model']}\" (status 404; pulled and spelled right?)"
        return f"the local model failed (status {code})"
    return f"could not reach the local model at {where}"


def _local_stream(cfg: dict[str, Any], system: str, messages: list[dict[str, Any]],
                  client: Any = None) -> Iterator[str]:
    import httpx
    body = {"model": cfg["model"], "stream": True, "max_tokens": LOCAL_MAX_TOKENS, "temperature": 0.3,
            "messages": [{"role": "system", "content": system}, *messages]}
    try:
        body.update(_extra_body())
    except LLMError as e:
        yield f"(The assistant failed: {e}.)"
        return
    http = _local_client(cfg, client)
    finish = None
    try:
        with http.stream("POST", _local_url(cfg), json=body) as r:
            if r.status_code >= 400:
                r.read()
                r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    choice = (json.loads(data).get("choices") or [{}])[0]
                except ValueError:
                    continue
                text = (choice.get("delta") or {}).get("content")
                if text:
                    yield text
                finish = choice.get("finish_reason") or finish
    except httpx.HTTPError as e:
        yield f"(The assistant failed: {_local_error(e, cfg)}.)"
        return
    finally:
        if client is None:
            http.close()
    if finish == "length":
        yield "\n\n(The answer was cut off.)"


def _local_json(cfg: dict[str, Any], system: str, user: str, schema: dict[str, Any],
                client: Any = None) -> dict[str, Any]:
    import httpx
    http = _local_client(cfg, client)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    base = {"model": cfg["model"], "stream": False, "max_tokens": LOCAL_JSON_MAX_TOKENS, "temperature": 0,
            **_extra_body()}
    strict = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True, "schema": schema}}
    try:
        r = http.post(_local_url(cfg), json={**base, "messages": messages, "response_format": strict})
        if r.status_code == 400:
            # a server without json_schema support: JSON mode, with the schema spelled out
            hint = ("\n\nAnswer with one JSON object only, no other text, that follows this JSON schema:\n"
                    + json.dumps(schema, ensure_ascii=False))
            messages[0] = {"role": "system", "content": system + hint}
            r = http.post(_local_url(cfg), json={**base, "messages": messages,
                                                  "response_format": {"type": "json_object"}})
        r.raise_for_status()
        choice = (r.json().get("choices") or [{}])[0]
    except httpx.HTTPError as e:
        raise LLMError(_local_error(e, cfg))
    except ValueError:
        raise LLMError("the local endpoint gave no valid response")
    finally:
        if client is None:
            http.close()
    if choice.get("finish_reason") == "length":
        raise LLMError("the local model's answer was cut off")
    return parse_json((choice.get("message") or {}).get("content") or "")
