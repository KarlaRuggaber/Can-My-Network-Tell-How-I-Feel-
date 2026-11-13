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
    c = login(portal, "anna", "pw-anna")
    cfg = c.get("/api/config").json()
    tl = c.get("/api/profiles/tester").json()
    assert tl["status"] == "ready" and tl["profile"]["has_plan"]
    assert tl["profile"]["phase_labels"] == {"baseline": "Baseline", "current": "Clinical"}
    d0, d1 = tl["days"]
    assert (d0["date"], d0["phase"], d0["complete"]) == ("2026-11-08", "baseline", True)
    assert d1["complete"] is False and d1["ground_truth"]["n_sensitive"] == 1
    assert d0["L"]["C3"] is None and 0.0 <= d0["L"]["C1"] <= 1.0
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
