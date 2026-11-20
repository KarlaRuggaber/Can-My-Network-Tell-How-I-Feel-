"""Login, roles, person profiles with their own devices, and the per-profile API."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from cmn_frontend import auth
from cmn_frontend.api import create_app
from cmn_frontend.export import export_dataset, tasks
from cmn_frontend.profiles import Device, Profile, ProfileStore
from cmn_frontend.store import DayStore
from fixtures import DS, PHONE_IP, make_run

RESOLVER_IP = "10.42.1.1"


@pytest.fixture(scope="module")
def portal(tmp_path_factory):
    s = make_run(tmp_path_factory.mktemp("portal"))
    export_dataset(DS, s)
    store = ProfileStore(s)
    assert store.all() == []                       # no scripted persona in the synthetic run
    store.upsert(Profile("tester", "Tester", DS, all_devices=True,
                         devices=[Device(PHONE_IP, "test_a_phone")]))
    store.upsert(Profile("dns", "Resolver only", DS, all_devices=False, devices=[Device(RESOLVER_IP, "router")],
                         baseline_first="2026-11-08", baseline_last="2026-11-08"))
    users = auth.UserStore(s.home_dir)
    users.add("doc", "pw-doc", "multi", ["*"])
    users.add("anna", "pw-anna", "single", ["tester"])
    return s


def login(s, user, pw):
    c = TestClient(create_app(s))
    r = c.post("/api/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return c


def test_passwords_and_sessions(tmp_path):
    h = auth.hash_password("secret")
    assert h.startswith("scrypt$") and "secret" not in h
    assert auth.check_password("secret", h) and not auth.check_password("Secret", h)
    tok = auth.make_session(tmp_path, "anna", now=1000)
    assert auth.read_session(tmp_path, tok, now=1001) == "anna"
    assert auth.read_session(tmp_path, tok, now=1000 + auth.SESSION_SECONDS + 1) is None   # expired
    body, sig = tok.rsplit(".", 1)
    assert auth.read_session(tmp_path, body + "." + "0" * len(sig), now=1001) is None      # forged
    with pytest.raises(ValueError):
        auth.UserStore(tmp_path).add("x", "pw", "single", ["a", "b"])


def test_login_required(portal):
    c = TestClient(create_app(portal))
    assert c.get("/api/health").status_code == 200
    assert c.get("/api/profiles").status_code == 401
    assert c.post("/api/login", json={"username": "doc", "password": "wrong"}).status_code == 401
    c = login(portal, "doc", "pw-doc")
    assert c.get("/api/me").json()["role"] == "multi"
    c.post("/api/logout")
    assert c.get("/api/me").status_code == 401


def test_single_user_sees_only_own_profile(portal):
    c = login(portal, "anna", "pw-anna")
    assert [p["id"] for p in c.get("/api/profiles").json()] == ["tester"]
    assert c.get("/api/profiles/dns").status_code == 404
    assert c.get("/api/sources").status_code == 403
    assert c.put("/api/profiles/tester", json={"name": "x", "source": DS}).status_code == 403


def test_timeline_from_plan(portal):
    c = login(portal, "doc", "pw-doc")          # the plan is only shown to multi-profile users
    cfg = c.get("/api/config").json()
    tl = c.get("/api/profiles/tester").json()
    assert tl["status"] == "ready" and tl["profile"]["has_plan"]
    assert tl["profile"]["phase_labels"] == {"baseline": "Baseline", "current": "Clinical"}
    d0, d1 = tl["days"]
    assert (d0["date"], d0["phase"], d0["complete"]) == ("2026-11-08", "baseline", True)
    assert d1["complete"] is False and d1["ground_truth"]["n_sensitive"] == 1
    assert d0["L"]["C3"] is None and 0.0 <= d0["L"]["C1"] <= 1.0
    assert len(d0["hourly"]) == 24 and sum(d0["hourly"]) == d0["packets_kept"]
    assert d0["hourly"][8] > 0 and d0["hourly"][3] == 0                   # partitions at 08, 12, 23 h
    assert any(k.startswith("C9_") for k in d0["metrics"])               # unscored criteria computed too
    configured = {k for k, v in cfg["criteria"].items() if v}
    base = tl["gate"]["phases"]["baseline"]
    assert base["counted"] == ["2026-11-08"] and set(base["criteria"]) == configured
    assert set(tl["gate"]["rolling"]["present"]) == configured
    day = c.get("/api/profiles/tester/days/2026-11-09").json()
    assert [b["block_id"] for b in day["blocks"]] == ["b2", "b3"]
    assert c.get("/api/profiles/tester/days/2026-01-01").status_code == 404
    assert c.get("/api/profiles/tester/days/xx").status_code == 400


def test_device_profile_is_computed_on_its_devices_only(portal):
    c = login(portal, "doc", "pw-doc")
    tl = c.get("/api/profiles/dns").json()
    assert tl["status"] == "pending" and tl["days"] == []           # not exported yet
    todo = tasks(portal, None)
    assert [t[2] for t in todo] == [DS, ProfileStore(portal).get("dns").cache_name]
    src, ips, name, labels = todo[1]
    assert ips == [RESOLVER_IP] and name.startswith(DS + "/@dev-")
    export_dataset(src, portal, ips=ips, cache_name=name, labels=labels)
    store = DayStore(portal.cache_dir)
    whole, mine = store.load(DS, date(2026, 11, 8)), store.load(name, date(2026, 11, 8))
    assert 0 < mine["packets_kept"] < whole["packets_kept"]          # only the resolver's packets
    assert list(mine["activity"]["devices"]) == ["router"]
    assert store.datasets() == [DS]                                  # device views are not sources
    tl = c.get("/api/profiles/dns").json()
    assert tl["status"] == "ready"
    assert tl["profile"]["phase_labels"]["current"] == "Clinical"   # the source's plan sets the phases


def test_live_source_uses_profile_baseline():
    """Without a plan (live traffic) the profile's baseline period splits the days."""
    from cmn_frontend.api import _periods
    days = [date(2026, 11, d) for d in range(1, 21)]
    p = Profile("x", "X", "live", baseline_first="2026-11-03", baseline_last="2026-11-09")
    phase, spans = _periods(p, days, {})
    assert phase[date(2026, 11, 2)] == "before" and phase[date(2026, 11, 3)] == "baseline"
    assert phase[date(2026, 11, 9)] == "baseline" and phase[date(2026, 11, 10)] == "current"
    assert spans["baseline"]["planned_days"] == 7 and spans["current"]["planned_first"] == "2026-11-10"
    phase, spans = _periods(Profile("y", "Y", "live"), days, {})      # default: first 14 days
    assert sum(v == "baseline" for v in phase.values()) == 14 and phase[days[-1]] == "current"


# ---- person view and explanation assistant ----

class _FakeStream:
    def __init__(self, calls, kw):
        calls.append(kw)
        self.text_stream = iter(["Your sleep ", "looks as usual."])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return type("M", (), {"stop_reason": "end_turn"})()


class FakeClaude:
    def __init__(self):
        self.calls = []
        msgs = type("Msgs", (), {"stream": lambda _s, **kw: _FakeStream(self.calls, kw)})()
        self.beta = type("Beta", (), {"messages": msgs})()


@pytest.fixture()
def scripted(portal):
    """A profile with a scripted persona's expectations, visible to anna (single) and doc (multi)."""
    store = ProfileStore(portal)
    store.upsert(Profile("ben2", "Ben", DS, all_devices=True, persona="gw_insomnia_a"))
    auth.UserStore(portal.home_dir).add("ben", "pw-ben", "single", ["ben2"])
    yield "ben2"
    store.delete("ben2")


def test_person_sees_no_expectations_or_plan(portal, scripted):
    doc = login(portal, "doc", "pw-doc").get(f"/api/profiles/{scripted}").json()
    assert doc["persona"]["expected"] and doc["persona"]["condition"]           # clinician: all of it
    me = login(portal, "ben", "pw-ben")
    tl = me.get(f"/api/profiles/{scripted}").json()
    assert tl["persona"]["expected"] == {} and tl["persona"]["episode"] is None
    assert tl["persona"]["condition"] == "" and tl["persona"]["summary"] == ""
    assert tl["profile"]["persona"] is None and tl["profile"]["phase_labels"]["current"] == "Recent"
    assert all(d["ground_truth"] is None for d in tl["days"])
    assert me.get(f"/api/profiles/{scripted}/days/2026-11-09").json()["blocks"] == []
    assert me.get("/api/profiles").json()[0]["condition"] == ""
    day = me.get(f"/api/profiles/{scripted}/days/2026-11-09").json()
    assert list(day["activity"]["devices"]) == ["Device 1"]
    assert all(d["metrics"] == {} for d in tl["days"])                     # no raw metrics for the person
    assert not any(k.startswith("C9_") for k in tl["baseline_stats"])
    assert all(not f["sensitive"] for f in tl["observed"]["flags"])
    assert "observed" in doc and doc["observed"]["tracks"][-1]["key"] == "sensitive_days"
    text = (str(tl) + str(me.get("/api/profiles").json()) + str(day)).lower()
    for word in ("insomnia", "elevated", DS, "test_a_phone"):
        assert word not in text, word


def test_assistant_is_off_by_default(portal, monkeypatch):
    for v in ("CMN_ASSISTANT", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    c = login(portal, "anna", "pw-anna")
    assert c.get("/api/assistant").json()["enabled"] is False
    r = c.post("/api/profiles/tester/assistant", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503


def test_assistant_explains_from_derived_results_only(portal, scripted, monkeypatch):
    monkeypatch.setenv("CMN_ASSISTANT", "1")
    fake = FakeClaude()
    app = create_app(portal, llm_client=fake)
    c = TestClient(app)
    c.post("/api/login", json={"username": "ben", "password": "pw-ben"})
    r = c.post(f"/api/profiles/{scripted}/assistant",
               json={"messages": [{"role": "user", "content": "Why is my sleep marked?"}], "focus": "Sleep"})
    assert r.status_code == 200 and r.text.split("\x1e")[0] == "Your sleep looks as usual."
    kw = fake.calls[-1]
    assert kw["model"] == "claude-sonnet-5-5" and kw["thinking"] == {"type": "adaptive"}
    assert kw["messages"][-1]["content"].endswith("Why is my sleep marked?")
    system = " ".join(b["text"] for b in kw["system"])
    assert "Do not use\n  DSM-5 criterion names" in system                     # person rules
    data = kw["system"][-1]["text"]
    assert "cache_control" in kw["system"][-1]
    for secret in (PHONE_IP, RESOLVER_IP, "test_a_phone", "151.101", "nzz", "expected", "Insomnia"):
        assert secret not in data, secret
    assert "Sleep" in data and "C4" not in data and "unscored_criteria" not in data and "C9" not in data
    assert "time of the first activity in the morning" in data and "WakeAfter0400" not in data

    # a clinician gets criterion names and the script's expectations, marked as such
    c = TestClient(app)
    c.post("/api/login", json={"username": "doc", "password": "pw-doc"})
    c.post(f"/api/profiles/{scripted}/assistant", json={"messages": [{"role": "user", "content": "C4?"}]})
    data = fake.calls[-1]["system"][-1]["text"]
    assert "C4 Sleep" in data and "scripted_expectations" in data and PHONE_IP not in data
    assert "unscored_criteria" in data and "C9 Suicidality" in data
    bad = c.post(f"/api/profiles/{scripted}/assistant", json={"messages": [{"role": "assistant", "content": "x"}]})
    assert bad.status_code == 422


def test_assistant_settings_claude_only(portal, scripted, monkeypatch):
    import json
    import os
    for v in ("CMN_ASSISTANT", "CMN_ASSISTANT_MODEL", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("cmn_frontend.assistant._anthropic_profile", lambda: False)  # no `ant auth login` profile
    path = portal.home_dir / "assistant.json"
    # an older settings file with an OpenRouter key: ignored, and dropped on the next save
    path.write_text(json.dumps({"enabled": True, "provider": "openrouter", "models": {"openrouter": "x"},
                                "api_keys": {"openrouter": "sk-or-old"}}))
    fake = FakeClaude()
    app = create_app(portal, llm_client=fake)
    person, doc = TestClient(app), TestClient(app)
    person.post("/api/login", json={"username": "ben", "password": "pw-ben"})
    doc.post("/api/login", json={"username": "doc", "password": "pw-doc"})
    assert person.put("/api/assistant", json={"enabled": True, "model": "x"}).status_code == 403
    st = doc.get("/api/assistant").json()
    assert st["model"] == "claude-sonnet-5-5" and st["default_model"] == "claude-sonnet-5-5"
    assert st["enabled"] is False and st["has_key"] is False and st["provider"] == "anthropic"  # no Claude key yet

    r = doc.put("/api/assistant", json={"enabled": True, "model": "claude-sonnet-5-5", "api_key": "sk-ant-test"})
    assert r.status_code == 200 and r.json()["has_key"] and "sk-ant-test" not in r.text
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    stored = json.loads(path.read_text())
    assert stored["api_keys"] == {"anthropic": "sk-ant-test"} and "openrouter" not in stored["models"]
    assert "sk-ant-test" not in doc.get("/api/assistant").text
    assert set(person.get("/api/assistant").json()) == {"enabled", "notice"}     # person: no settings
    doc.put("/api/assistant", json={"enabled": True, "model": "claude-sonnet-5-5"})   # no key: keep it
    assert json.loads(path.read_text())["api_keys"]["anthropic"] == "sk-ant-test"

    r = person.post(f"/api/profiles/{scripted}/assistant", json={"messages": [{"role": "user", "content": "Sleep?"}]})
    assert r.status_code == 200 and fake.calls[-1]["model"] == "claude-sonnet-5-5"

    doc.put("/api/assistant", json={"enabled": False, "model": "claude-sonnet-5-5", "api_key": ""})
    assert json.loads(path.read_text())["api_keys"] == {}
    path.unlink()


def test_assistant_on_a_local_model(portal, scripted, monkeypatch):
    """Provider "local": the same context goes to an OpenAI-compatible endpoint, nothing to Anthropic."""
    import json
    import httpx
    for v in ("CMN_ASSISTANT", "CMN_ASSISTANT_PROVIDER", "CMN_ASSISTANT_MODEL", "ANTHROPIC_API_KEY", "CMN_LOCAL_URL"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr("cmn_frontend.assistant._anthropic_profile", lambda: False)
    sent = []

    def server(req: httpx.Request) -> httpx.Response:
        sent.append((str(req.url), json.loads(req.content)))
        chunk = json.dumps({"choices": [{"delta": {"content": "Quieter nights."}, "finish_reason": "stop"}]})
        return httpx.Response(200, content=f"data: {chunk}\n\ndata: [DONE]\n\n".encode())
    app = create_app(portal, llm_client=httpx.Client(transport=httpx.MockTransport(server)))
    person, doc = TestClient(app), TestClient(app)
    person.post("/api/login", json={"username": "ben", "password": "pw-ben"})
    doc.post("/api/login", json={"username": "doc", "password": "pw-doc"})
    assert doc.put("/api/assistant", json={"enabled": True, "model": "qwen2.5:3b", "provider": "local",
                                           "base_url": "ftp://x"}).status_code == 422
    r = doc.put("/api/assistant", json={"enabled": True, "model": "qwen2.5:3b", "provider": "local",
                                        "base_url": "http://100.64.0.5:11434/v1"})
    assert r.status_code == 200 and r.json()["provider"] == "local" and r.json()["has_key"] is True
    assert person.get("/api/assistant").json()["enabled"] is True          # no Claude key needed
    assert person.get("/api/assistant").json()["notice"] == ""
    r = person.post(f"/api/profiles/{scripted}/assistant", json={"messages": [{"role": "user", "content": "Sleep?"}]})
    assert r.status_code == 200 and r.text.split("\x1e")[0] == "Quieter nights."
    url, body = sent[-1]
    assert url == "http://100.64.0.5:11434/v1/chat/completions" and body["model"] == "qwen2.5:3b"
    assert body["messages"][0]["role"] == "system" and "<results>" in body["messages"][0]["content"]
    assert PHONE_IP not in json.dumps(body) and "C4" not in body["messages"][0]["content"].split("<results>")[1]
    doc.put("/api/assistant", json={"enabled": False, "model": "claude-sonnet-5-5", "provider": "anthropic"})
    (portal.home_dir / "assistant.json").unlink()


def test_notes_and_seen_flags_for_clinicians_only(portal):
    doc = login(portal, "doc", "pw-doc")
    anna = login(portal, "anna", "pw-anna")
    r = doc.post("/api/profiles/tester/notes", json={"date": "2026-11-08", "text": "  Exam week  "})
    assert r.status_code == 200 and r.json()["notes"][0]["text"] == "Exam week"
    assert r.json()["notes"][0]["author"] == "doc"
    assert doc.post("/api/profiles/tester/notes", json={"date": "08.11.2026", "text": "x"}).status_code == 400
    assert doc.post("/api/profiles/tester/notes", json={"date": "2026-11-08", "text": "   "}).status_code == 422
    tl = doc.get("/api/profiles/tester").json()
    assert [n["text"] for n in tl["notes"]] == ["Exam week"] and tl["seen"] == {}
    # the person neither reads nor writes notes
    assert "notes" not in anna.get("/api/profiles/tester").json()
    assert anna.post("/api/profiles/tester/notes", json={"date": "2026-11-08", "text": "hi"}).status_code == 403
    # seen marks
    r = doc.put("/api/profiles/tester/flags/later_nights/seen", json={"last_day": "2026-11-08"})
    assert r.json()["seen"]["later_nights"]["by"] == "doc"
    assert doc.delete("/api/profiles/tester/flags/later_nights/seen").json()["seen"] == {}
    nid = tl["notes"][0]["id"]
    assert doc.delete(f"/api/profiles/tester/notes/{nid}").json()["notes"] == []
    assert doc.delete(f"/api/profiles/tester/notes/{nid}").status_code == 404


def test_healthy_reference_setting(portal):
    from cmn_frontend.profiles import Profile as P
    doc = login(portal, "doc", "pw-doc")
    body = {"name": "Resolver only", "source": DS, "all_devices": False,
            "devices": [{"ip": RESOLVER_IP, "label": "router"}], "reference": "bogus"}
    assert doc.put("/api/profiles/dns", json=body).status_code == 422
    body["reference"] = "all"
    r = doc.put("/api/profiles/dns", json=body).json()
    assert r["reference"] == "all" and r["reference_mode"] == "all"
    assert P("x", "X", "s").reference_mode == "none" and P("x", "X", "s", persona="gw_a").reference_mode == "baseline"
    body["reference"] = None
    assert doc.put("/api/profiles/dns", json=body).json()["reference_mode"] == "none"


def test_dictation_goes_to_the_local_whisper_service_only(portal, monkeypatch):
    import httpx
    monkeypatch.delenv("CMN_WHISPER_URL", raising=False)
    seen = []

    def whisper(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"ok": True, "model": "small", "max_seconds": 300})
        if request.content == b"noise":
            return httpx.Response(415, json={"detail": "could not read the recording"})
        return httpx.Response(200, json={"text": " School from eight to four. ", "language": "en", "seconds": 3.2})

    app = create_app(portal, speech_transport=httpx.MockTransport(whisper))
    anon = TestClient(app)
    assert anon.post("/api/transcribe", content=b"x", headers={"content-type": "audio/webm"}).status_code == 401
    me = TestClient(app)
    me.post("/api/login", json={"username": "anna", "password": "pw-anna"})       # the person may dictate too
    assert me.get("/api/transcribe").json()["available"] is True
    r = me.post("/api/transcribe", content=b"\x1aE\xdf\xa3webm", headers={"content-type": "audio/webm;codecs=opus"})
    assert r.status_code == 200 and r.json()["text"] == "School from eight to four."
    req = seen[-1]
    assert str(req.url) == "http://127.0.0.1:8601/transcribe" and req.content == b"\x1aE\xdf\xa3webm"
    assert req.headers["content-type"] == "audio/webm;codecs=opus" and "cookie" not in req.headers
    assert me.post("/api/transcribe", content=b"noise", headers={"content-type": "audio/webm"}).status_code == 422
    assert me.post("/api/transcribe", content=b"{}", headers={"content-type": "application/json"}).status_code == 415
    assert me.post("/api/transcribe", content=b"", headers={"content-type": "audio/webm"}).status_code == 400

    # service down: dictation is shown as unavailable, and a recording gets a short note
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    app = create_app(portal, speech_transport=httpx.MockTransport(down))
    me = TestClient(app)
    me.post("/api/login", json={"username": "anna", "password": "pw-anna"})
    assert me.get("/api/transcribe").json() == {"available": False}
    r = me.post("/api/transcribe", content=b"a", headers={"content-type": "audio/webm"})
    assert r.status_code == 503 and "not running" in r.json()["detail"]

    monkeypatch.setenv("CMN_WHISPER_URL", "off")                                     # turned off
    me = TestClient(create_app(portal))
    me.post("/api/login", json={"username": "anna", "password": "pw-anna"})
    assert me.get("/api/transcribe").json() == {"available": False}
