"""Onboarding and care plan: routine, away periods, clinical setup, and their effect on the analysis."""

import json

import pytest
from fastapi.testclient import TestClient

from cmn_frontend import care, observed as ob
from cmn_frontend.api import create_app
from fixtures import DS, make_run
from test_observed import _days


def test_routine_is_cleaned_and_validated():
    r = care.clean_routine({"week": {"wed": "home"}, "bedtime": "23:30",
                            "devices": [{"name": " iPhone ", "kind": "phone"}, {"name": ""}]})
    assert r["week"]["mon"] == {"am": "away", "pm": "away"} and r["week"]["wed"] == {"am": "home", "pm": "home"}
    assert r["week"]["sat"] == {"am": "free", "pm": "free"}       # a single type (older routines): the whole day
    assert r["bedtime"] == "23:30" and r["wake"] is None
    assert [d["name"] for d in r["devices"]] == ["iPhone"] and r["devices"][0]["ip"] is None
    for bad in ({"week": {"mon": "sometimes"}}, {"bedtime": "25:00"}, {"devices": [{"name": "x", "kind": "toaster"}]}):
        with pytest.raises(ValueError):
            care.clean_routine(bad)
    with pytest.raises(ValueError):
        care.clean_away([{"from": "2026-11-10", "to": "2026-11-01"}])


def test_purpose_is_validated_and_sets_the_change_flag_default():
    risk_ids, tracks = ["later_nights", "sensitive_sites"], ["quiet_start"]
    c = care.clean_clinical({}, risk_ids, tracks)
    assert c["purpose"] == "assessment" and c["change_flags"] is None
    assert care.purpose_of(None) == "assessment" and care.change_flags_on(None) is True
    t = care.clean_clinical({"purpose": "treatment"}, risk_ids, tracks)
    assert care.purpose_of(t) == "treatment" and care.change_flags_on(t) is True
    # the clinician's explicit choice wins over the purpose's default, in both directions
    assert care.change_flags_on(care.clean_clinical({"purpose": "treatment", "change_flags": False}, risk_ids, tracks)) is False
    assert care.change_flags_on(care.clean_clinical({"purpose": "assessment", "change_flags": True}, risk_ids, tracks)) is True
    for bad in ({"purpose": "screening"}, {"change_flags": "yes"}):
        with pytest.raises(ValueError):
            care.clean_clinical(bad, risk_ids, tracks)
    # crisis or self-harm sites are a safety signal: never switched off
    c = care.clean_clinical({"focus": {"sensitive_sites": {"enabled": False}, "later_nights": {"enabled": False}}},
                            risk_ids, tracks)
    assert c["focus"]["sensitive_sites"]["enabled"] is True and c["focus"]["later_nights"]["enabled"] is False


def test_change_flags_are_on_unless_switched_off():
    flags = [{"id": "later_nights", "kind": "risk"}, {"id": "earlier_nights", "kind": "change"},
             {"id": "sensitive_sites"}]                       # flags without a kind are risk flags (v2)
    ids = lambda clinical: [f["id"] for f in care.apply_purpose(flags, clinical)]
    assert ids(None) == ["later_nights", "earlier_nights", "sensitive_sites"]          # on by default
    assert ids({"purpose": "assessment"}) == ["later_nights", "earlier_nights", "sensitive_sites"]
    assert ids({"purpose": "assessment", "change_flags": False}) == ["later_nights", "sensitive_sites"]
    assert ids({"purpose": "treatment"}) == ["later_nights", "earlier_nights", "sensitive_sites"]
    assert ids({"purpose": "treatment", "change_flags": False}) == ["later_nights", "sensitive_sites"]
    assert ids({"purpose": "assessment", "change_flags": True}) == ["later_nights", "earlier_nights", "sensitive_sites"]


def test_day_type_from_routine_and_away_periods():
    r = care.clean_routine({"week": {"wed": "home"}})
    away = care.clean_away([{"from": "2026-11-20", "to": "2026-11-22", "reason": "holidays"}])
    assert care.day_type(r, away, "2026-11-18") == "home"          # a Wednesday
    assert care.day_type(r, away, "2026-11-16") == "away"          # a Monday
    assert care.day_type(r, away, "2026-11-21") == "away_period"
    assert care.day_type(None, [], "2026-11-21") is None


def test_morning_and_afternoon_per_weekday():
    r = care.clean_routine({"week": {"mon": {"am": "away", "pm": "free"}, "tue": {"am": "home", "pm": "free"},
                                     "sat": {"am": "free"}}})
    assert r["week"]["mon"] == {"am": "away", "pm": "free"} and r["week"]["sat"] == {"am": "free", "pm": "free"}
    assert care.day_type(r, [], "2026-11-16") == "away"            # Monday: school in the morning
    assert care.day_type(r, [], "2026-11-17") == "home"            # Tuesday: home office, then free
    assert care.day_type(r, [], "2026-11-21") == "free"
    with pytest.raises(ValueError):
        care.clean_routine({"week": {"mon": {"am": "away", "pm": "later"}}})


def test_focus_sensitivity_normals_and_away_periods_change_the_flags():
    days, acts = _days(10, 7, late_cur=4)
    base_flags = {f["id"] for f in ob.build(days, acts, {})["flags"]}
    assert "later_nights" in base_flags

    days, acts = _days(10, 7, late_cur=4)
    assert "later_nights" not in {f["id"] for f in ob.build(days, acts, {}, focus={"later_nights": {"enabled": False}})["flags"]}

    # relaxed needs 4 of 7: 4 late nights still flag, 2 do not
    days, acts = _days(10, 7, late_cur=2)
    out = ob.build(days, acts, {}, focus={"later_nights": {"enabled": True, "sensitivity": "relaxed"}})
    assert "later_nights" not in {f["id"] for f in out["flags"]}
    days, acts = _days(10, 7, late_cur=2)
    out = ob.build(days, acts, {}, focus={"later_nights": {"enabled": True, "sensitivity": "strict"}})
    assert "later_nights" in {f["id"] for f in out["flags"]}

    # a clinician's normal bedtime range that includes the late nights: no flag
    days, acts = _days(10, 7, late_cur=4)
    out = ob.build(days, acts, {}, normals={"quiet_start": {"min": -120, "max": 180}})
    assert "later_nights" not in {f["id"] for f in out["flags"]} and out["normals"]["quiet_start"]["max"] == 180

    # the late nights fall into a stated away period (holidays): left out of the flags
    days, acts = _days(10, 7, late_cur=4)
    types = {d["date"]: ("away_period" if d["phase"] == "current" else None) for d in days}
    assert "later_nights" not in {f["id"] for f in ob.build(days, acts, {}, day_types=types)["flags"]}


def test_usual_range_per_day_type():
    days, acts = _days(14, 0, late_cur=0)
    types = {d["date"]: ("free" if i % 7 in (5, 6) else "away") for i, d in enumerate(days)}
    out = ob.build(days, acts, {}, day_types=types)
    assert "away" in out["usual_by_type"] and "free" not in out["usual_by_type"]     # 10 away days, 4 free days
    assert all(d["observed"]["day_type"] in ("away", "free") for d in days)


class _FakeMsg:
    def __init__(self, text):
        self.stop_reason = "end_turn"
        self.content = [type("B", (), {"type": "text", "text": text})()]


class FakeClaude:
    def __init__(self, payload):
        self.calls, payload_text = [], json.dumps(payload)
        msgs = type("M", (), {"create": lambda _s, **kw: (self.calls.append(kw), _FakeMsg(payload_text))[1]})()
        self.beta = type("Beta", (), {"messages": msgs})()


@pytest.fixture()
def portal(tmp_path, monkeypatch):
    from cmn_frontend import auth
    from cmn_frontend.export import export_dataset
    from cmn_frontend.profiles import Profile, ProfileStore
    monkeypatch.setenv("CMN_ASSISTANT", "1")
    s = make_run(tmp_path)
    export_dataset(DS, s)
    ProfileStore(s).upsert(Profile("pat", "Pat", DS))
    users = auth.UserStore(s.home_dir)
    users.add("doc", "pw-doc", "multi", ["*"])
    users.add("pat", "pw-pat", "single", ["pat"])
    return s


def _client(s, user, pw, llm=None):
    c = TestClient(create_app(s, llm_client=llm))
    assert c.post("/api/login", json={"username": user, "password": pw}).status_code == 200
    return c


def test_onboarding_and_care_plan_permissions(portal):
    pat, doc = _client(portal, "pat", "pw-pat"), _client(portal, "doc", "pw-doc")
    r = pat.put("/api/profiles/pat/care/routine", json={"routine": {
        "week": {"wed": "home"}, "bedtime": "23:00", "devices": [{"id": "d1", "name": "iPhone", "kind": "phone"}]}})
    assert r.status_code == 200 and r.json()["clinical"] is None
    # the clinician links the iPhone to an address; the patient's later edit keeps the link
    rt = doc.get("/api/profiles/pat").json()["care"]["routine"]
    rt["devices"][0]["ip"] = "10.42.1.21"
    assert doc.put("/api/profiles/pat/care/routine", json={"routine": rt}).status_code == 200
    rt["devices"][0]["ip"] = None
    rt["bedtime"] = "23:30"
    pat.put("/api/profiles/pat/care/routine", json={"routine": rt})
    after = doc.get("/api/profiles/pat").json()["care"]["routine"]
    assert after["devices"][0]["ip"] == "10.42.1.21" and after["bedtime"] == "23:30"
    # clinical setup: clinicians and parents only, never in the patient's view
    clinical = {"history": "Depressive episode 2025.", "concerns": "Sleep", "criteria": ["C4", "C9"],
                "focus": {"later_nights": {"enabled": True, "sensitivity": "strict"}},
                "normals": {"quiet_start": {"min": -60, "max": 30}}}
    assert pat.put("/api/profiles/pat/care/clinical", json={"clinical": clinical}).status_code == 403
    assert doc.put("/api/profiles/pat/care/clinical", json={"clinical": {"criteria": ["C10"]}}).status_code == 422
    assert doc.get("/api/profiles/pat").json()["care"]["purpose"] == "assessment"     # default before any setup
    assert doc.put("/api/profiles/pat/care/clinical", json={"clinical": {"purpose": "screening"}}).status_code == 422
    clinical["purpose"] = "treatment"
    saved = doc.put("/api/profiles/pat/care/clinical", json={"clinical": clinical}).json()
    assert saved["clinical"]["criteria"] == ["C4", "C9"]
    assert saved["purpose"] == "treatment" and saved["change_flags"] is True and saved["clinical"]["purpose"] == "treatment"
    tl_pat = pat.get("/api/profiles/pat").json()
    assert tl_pat["care"]["clinical"] is None and "Depressive" not in json.dumps(tl_pat)
    assert "purpose" not in tl_pat["care"] and "treatment" not in json.dumps(tl_pat["care"])
    tl_doc = doc.get("/api/profiles/pat").json()
    assert tl_doc["care"]["purpose"] == "treatment" and tl_doc["care"]["change_flags"] is True
    assert tl_pat["observed"]["focus"] == {}
    tl_doc = doc.get("/api/profiles/pat").json()
    assert tl_doc["observed"]["focus"]["later_nights"]["sensitivity"] == "strict"
    assert tl_doc["observed"]["normals"]["quiet_start"]["max"] == 30
    assert "observability" in doc.get("/api/config").json() and "observability" not in pat.get("/api/config").json()
    # away periods by the patient
    r = pat.put("/api/profiles/pat/care/away", json={"away_periods": [{"from": "2026-11-09", "to": "2026-11-09", "reason": "trip"}]})
    assert r.status_code == 200 and "purpose" not in r.json() and r.json()["clinical"] is None
    days = doc.get("/api/profiles/pat").json()["days"]
    assert [d["observed"]["day_type"] for d in days if d["date"] == "2026-11-09"] == ["away_period"]


def test_setup_suggestions_are_validated(portal):
    routine = {"week": {d: {"am": "away", "pm": "away"} for d in care.WEEKDAYS}, "away_from": "07:30",
               "away_to": "16:00", "bedtime": "22:30", "wake": "06:45", "bedtime_free": None, "wake_free": None,
               "devices": [{"name": "iPhone", "kind": "phone", "shared": False}], "note": ""}
    routine["week"]["wed"] = {"am": "away", "pm": "home"}
    routine["week"]["sat"] = routine["week"]["sun"] = {"am": "free", "pm": "free"}
    fake = FakeClaude(routine)
    pat = _client(portal, "pat", "pw-pat", fake)
    r = pat.post("/api/profiles/pat/setup-suggestion", json={"kind": "routine", "text": "School Mon-Fri, bed at 22:30"})
    assert r.status_code == 200 and r.json()["routine"]["away_from"] == "07:30"
    assert r.json()["routine"]["week"]["wed"] == {"am": "away", "pm": "home"}
    kw = fake.calls[-1]
    assert kw["output_config"]["format"]["type"] == "json_schema" and "School" in kw["messages"][0]["content"]
    week_schema = kw["output_config"]["format"]["schema"]["properties"]["week"]["properties"]["mon"]
    assert week_schema["required"] == ["am", "pm"]
    assert pat.post("/api/profiles/pat/setup-suggestion", json={"kind": "focus"}).status_code == 403
    assert pat.get("/api/profiles/pat").json()["care"]["routine"] is None        # nothing saved by a suggestion

    focus = {"criteria": [{"criterion": "C4", "priority": "high", "reason": "sleep"},
                          {"criterion": "C99", "priority": "high", "reason": "x"}],
             "risks": [{"id": "later_nights", "enabled": True, "sensitivity": "strict", "reason": "r"},
                       {"id": "sensitive_sites", "enabled": False, "sensitivity": "standard", "reason": "none reported"},
                       {"id": "made_up", "enabled": True, "sensitivity": "strict", "reason": "r"}],
             "caveats": ["shared iPad"]}
    doc = _client(portal, "doc", "pw-doc", FakeClaude(focus))
    assert doc.post("/api/profiles/pat/setup-suggestion", json={"kind": "focus"}).status_code == 422   # no notes yet
    r = doc.post("/api/profiles/pat/setup-suggestion", json={"kind": "focus", "text": "Insomnia since summer."})
    out = r.json()["focus"]
    assert [c["criterion"] for c in out["criteria"]] == ["C4"]
    assert [x["id"] for x in out["risks"]] == ["later_nights", "sensitive_sites"]
    assert out["risks"][1]["enabled"] is True and out["risks"][1]["reason"].startswith("Kept on")
