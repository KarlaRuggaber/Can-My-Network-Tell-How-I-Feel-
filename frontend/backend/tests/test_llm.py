"""Provider layer (llm.py): Anthropic and a local OpenAI-compatible endpoint, offline with fake servers."""

import json

import httpx
import pytest

from cmn_frontend import llm, setup_assist
from cmn_frontend.assistant import AssistantConfig

LOCAL = {"provider": "local", "model": "qwen2.5:3b", "api_key": "", "base_url": "http://laptop:11434/v1"}


def sse(*chunks: str, finish: str = "stop") -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': c}, 'finish_reason': None}]})}" for c in chunks]
    lines.append(f"data: {json.dumps({'choices': [{'delta': {}, 'finish_reason': finish}]})}")
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode()


class FakeServer:
    """An OpenAI-compatible /chat/completions; records the request bodies."""

    def __init__(self, handler):
        self.requests: list[dict] = []
        self.handler = handler

    def client(self) -> httpx.Client:
        def h(req: httpx.Request) -> httpx.Response:
            assert req.url.path == "/v1/chat/completions" and req.url.host == "laptop"
            body = json.loads(req.content)
            self.requests.append(body)
            return self.handler(body)
        return httpx.Client(transport=httpx.MockTransport(h))


def test_local_stream_joins_system_blocks_and_streams_text():
    srv = FakeServer(lambda b: httpx.Response(200, content=sse("Quiet ", "as usual."),
                                              headers={"content-type": "text/event-stream"}))
    system = [{"type": "text", "text": "Rules."},
              {"type": "text", "text": "<results>\n{}\n</results>", "cache_control": {"type": "ephemeral"}}]
    out = "".join(llm.stream_text(LOCAL, system, [{"role": "user", "content": "Sleep?"}], srv.client()))
    assert out == "Quiet as usual."
    body = srv.requests[-1]
    assert body["model"] == "qwen2.5:3b" and body["stream"] is True
    assert body["messages"][0] == {"role": "system", "content": "Rules.\n\n<results>\n{}\n</results>"}
    assert body["messages"][1] == {"role": "user", "content": "Sleep?"}
    assert "cache_control" not in json.dumps(body)


def test_local_stream_notes_cut_off_and_errors_instead_of_raising():
    srv = FakeServer(lambda b: httpx.Response(200, content=sse("Half", finish="length")))
    assert "".join(llm.stream_text(LOCAL, "s", [{"role": "user", "content": "q"}], srv.client())) \
        == "Half\n\n(The answer was cut off.)"
    srv = FakeServer(lambda b: httpx.Response(404, json={"error": "model not found"}))
    out = "".join(llm.stream_text(LOCAL, "s", [{"role": "user", "content": "q"}], srv.client()))
    assert out.startswith("(The assistant failed:") and "qwen2.5:3b" in out

    def down(req):
        raise httpx.ConnectError("refused")
    out = "".join(llm.stream_text(LOCAL, "s", [{"role": "user", "content": "q"}],
                                  httpx.Client(transport=httpx.MockTransport(down))))
    assert out == "(The assistant failed: could not reach the local model at http://laptop:11434/v1.)"


def _answer(content: str, finish: str = "stop") -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content},
                                                  "finish_reason": finish}]})


def test_local_json_uses_the_schema_as_grammar():
    routine = {"week": {d: {"am": "away", "pm": "free"} for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")},
               "away_from": "07:30", "away_to": None, "bedtime": "22:30", "wake": None, "bedtime_free": None,
               "wake_free": None, "devices": [{"name": "iPhone", "kind": "phone", "shared": False}], "note": ""}
    srv = FakeServer(lambda b: _answer(json.dumps(routine)))
    out = setup_assist.suggest_routine(LOCAL, "School Mon-Fri, bed at 22:30", client=srv.client())
    assert out["away_from"] == "07:30" and out["devices"][0]["name"] == "iPhone"
    body = srv.requests[-1]
    assert body["stream"] is False and body["temperature"] == 0
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["schema"] == setup_assist.ROUTINE_SCHEMA
    assert "School Mon-Fri" in body["messages"][1]["content"]


def test_local_json_falls_back_to_json_mode_and_strips_fences():
    def handler(b):
        if b["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": "response_format json_schema not supported"})
        return _answer('Here it is:\n```json\n{"caveats": ["shared iPad"]}\n```')
    srv = FakeServer(handler)
    schema = {"type": "object", "properties": {"caveats": {"type": "array"}}}
    assert llm.complete_json(LOCAL, "sys", "notes", schema, srv.client()) == {"caveats": ["shared iPad"]}
    assert [r["response_format"]["type"] for r in srv.requests] == ["json_schema", "json_object"]
    assert '"caveats"' in srv.requests[-1]["messages"][0]["content"]        # the schema is in the prompt


def test_local_json_errors_are_short_value_errors():
    srv = FakeServer(lambda b: _answer("no json here"))
    with pytest.raises(ValueError, match="no JSON"):
        llm.complete_json(LOCAL, "s", "u", {}, srv.client())
    srv = FakeServer(lambda b: _answer('{"a": [1, 2', finish="length"))
    with pytest.raises(ValueError, match="cut off"):
        llm.complete_json(LOCAL, "s", "u", {}, srv.client())
    srv = FakeServer(lambda b: httpx.Response(500, text="boom"))
    with pytest.raises(llm.LLMError, match="status 500"):
        llm.complete_json(LOCAL, "s", "u", {}, srv.client())


def test_api_key_is_sent_only_when_set(monkeypatch):
    seen = []

    class Recorder(httpx.Client):
        def __init__(self, **kw):
            seen.append(kw.get("headers"))
            super().__init__(transport=httpx.MockTransport(lambda r: _answer("{}")))
    monkeypatch.setattr(httpx, "Client", Recorder)
    llm.complete_json(LOCAL, "s", "u", {})
    llm.complete_json({**LOCAL, "api_key": "lm-secret"}, "s", "u", {})
    assert seen == [{}, {"Authorization": "Bearer lm-secret"}]


def test_config_keeps_model_key_and_endpoint_per_provider(tmp_path, monkeypatch):
    for v in ("CMN_ASSISTANT", "CMN_ASSISTANT_PROVIDER", "CMN_ASSISTANT_MODEL", "ANTHROPIC_API_KEY",
              "CMN_LOCAL_URL", "CMN_LOCAL_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("cmn_frontend.assistant._anthropic_profile", lambda: False)
    cfg = AssistantConfig(tmp_path)
    assert cfg.load()["provider"] == "anthropic" and "base_url" not in cfg.load()
    cfg.save(True, "claude-sonnet-5-5", "sk-ant-x")
    cfg.save(True, "qwen2.5:3b", None, provider="local", base_url="http://user:pw@100.64.0.5:11434/v1/")
    c = cfg.load()
    assert c == {"enabled": True, "provider": "local", "model": "qwen2.5:3b", "api_key": "",
                 "base_url": "http://user:pw@100.64.0.5:11434/v1"}
    pub = cfg.public()
    assert pub["has_key"] is True and pub["base_url"] == "http://100.64.0.5:11434/v1"   # no credentials shown
    assert pub["notice"] == ""   # local model: nothing leaves our computers, no notice
    assert [p["id"] for p in pub["providers"]] == ["anthropic", "local"]
    cfg.save(True, "claude-sonnet-5-5", None, provider="anthropic")          # back: Claude key still there
    assert cfg.load()["api_key"] == "sk-ant-x" and cfg.public()["base_url"] == "http://100.64.0.5:11434/v1"
    with pytest.raises(ValueError, match="http"):
        cfg.save(True, "m", None, provider="local", base_url="ftp://x")
    with pytest.raises(ValueError, match="unknown provider"):
        cfg.save(True, "m", None, provider="openrouter")


def test_config_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("CMN_ASSISTANT", "1")
    monkeypatch.setenv("CMN_ASSISTANT_PROVIDER", "local")
    monkeypatch.setenv("CMN_ASSISTANT_MODEL", "llama3.2:3b")
    monkeypatch.setenv("CMN_LOCAL_URL", "http://laptop.tail.ts.net:11434/v1")
    c = AssistantConfig(tmp_path).load()
    assert (c["enabled"], c["provider"], c["model"], c["base_url"]) == \
        (True, "local", "llama3.2:3b", "http://laptop.tail.ts.net:11434/v1")


def test_check_local_lists_the_served_models():
    def h(req):
        assert req.url.path == "/v1/models"
        return httpx.Response(200, json={"object": "list", "data": [{"id": "qwen2.5:3b"}, {"id": "llama3.2:3b"}]})
    c = httpx.Client(transport=httpx.MockTransport(h))
    assert llm.check_local("http://laptop:11434/v1", "qwen2.5:3b", client=c)["ok"] is True
    out = llm.check_local("http://laptop:11434/v1", "qwen3:4b", client=c)
    assert out["ok"] is False and "llama3.2:3b, qwen2.5:3b" in out["message"]

    def down(req):
        raise httpx.ConnectError("refused")
    out = llm.check_local("http://laptop:11434/v1", "m", client=httpx.Client(transport=httpx.MockTransport(down)))
    assert out == {"ok": False, "models": [], "message": "Could not reach the local model at http://laptop:11434/v1."}


def test_extra_body_from_the_environment(monkeypatch):
    srv = FakeServer(lambda b: httpx.Response(200, content=sse("ok")) if b["stream"] else _answer("{}"))
    monkeypatch.setenv("CMN_LOCAL_EXTRA_BODY", '{"reasoning_effort": "none"}')
    assert "".join(llm.stream_text(LOCAL, "s", [{"role": "user", "content": "q"}], srv.client())) == "ok"
    llm.complete_json(LOCAL, "s", "u", {}, srv.client())
    assert [r["reasoning_effort"] for r in srv.requests] == ["none", "none"]
    monkeypatch.setenv("CMN_LOCAL_EXTRA_BODY", "{nope")
    assert "not valid JSON" in "".join(llm.stream_text(LOCAL, "s", [{"role": "user", "content": "q"}], srv.client()))


def test_stream_answer_accepts_the_v2_client_name():
    from cmn_frontend import assistant
    srv = FakeServer(lambda b: httpx.Response(200, content=sse("hi")))
    assert "".join(assistant.stream_answer(LOCAL, "s", [{"role": "user", "content": "q"}],
                                           anthropic_client=srv.client())) == "hi"


def test_unreachable_local_model_falls_back_to_claude_only_when_configured():
    def down(req):
        raise httpx.ConnectError("refused")
    dead = httpx.Client(transport=httpx.MockTransport(down))
    calls = []

    class FakeStream:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        text_stream = iter(["From Claude."])
        def get_final_message(self):
            return type("M", (), {"stop_reason": "end_turn", "content": []})()

    class FakeClaude:
        class beta:
            class messages:
                @staticmethod
                def stream(**kw):
                    calls.append(kw["model"])
                    return FakeStream()
    cfg = {**LOCAL, "fallback": {"provider": "anthropic", "model": "claude-x", "api_key": "k"}}
    out = "".join(llm.stream_text(cfg, "s", [{"role": "user", "content": "q"}], dead, fallback_client=FakeClaude()))
    assert out.startswith("(The local model was not reachable, so Claude (Anthropic) answered.)") and out.endswith("From Claude.") and calls == ["claude-x"]
    # without a fallback the error note stays, and no Claude call is made
    out = "".join(llm.stream_text(LOCAL, "s", [{"role": "user", "content": "q"}], dead))
    assert out.startswith("(The assistant failed:")


def test_fallback_setting_is_saved_and_needs_a_claude_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("cmn_frontend.assistant._anthropic_profile", lambda: False)
    c = AssistantConfig(tmp_path)
    c.save(True, "qwen", None, "local", "http://laptop:11434/v1", fallback=True)
    assert c.public()["fallback"] is True and c.public()["fallback_ready"] is False and "fallback" not in c.load()
    c.save(True, "claude-x", "sk-test", "anthropic")
    c.save(True, "qwen", None, "local", None)          # fallback None: kept
    assert c.load()["fallback"]["model"] == "claude-x" and c.public()["notice"] == ""
    c.save(True, "qwen", None, "local", None, fallback=False)
    assert "fallback" not in c.load() and c.public()["fallback"] is False
