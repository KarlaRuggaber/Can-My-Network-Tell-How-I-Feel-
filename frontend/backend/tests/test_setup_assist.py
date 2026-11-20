"""Onboarding follow-up questions: what a description of the week left open (decided by rules)."""

import json

from cmn_frontend import care, setup_assist as sa


def _routine(**kw):
    base = {"week": {}, "away_from": "07:30", "away_to": "16:00", "bedtime": "22:30", "wake": "06:45",
            "bedtime_free": "00:00", "wake_free": "09:30", "devices": [{"name": "iPhone", "kind": "phone"}], "note": ""}
    base["week"] = {d: {"am": "away", "pm": "away"} for d in care.WEEKDAYS[:5]}
    base["week"]["wed"] = {"am": "away", "pm": "home"}
    base["week"].update({d: {"am": "free", "pm": "free"} for d in ("sat", "sun")})
    return care.clean_routine({**base, **kw})


def _ids(r):
    return [q["id"] for q in sa.missing_fields(r)]


def test_a_complete_routine_needs_no_questions():
    assert sa.missing_fields(_routine()) == []


def test_a_description_without_times_asks_for_everything_in_order():
    r = care.clean_routine({"week": {}})         # what the model returns for "I go to school"
    qs = sa.missing_fields(r)
    assert [q["id"] for q in qs] == ["week", "away_times", "sleep_workdays", "sleep_free", "devices"]
    assert qs[1]["fields"] == ["away_from", "away_to"]
    assert qs[3]["fields"] == ["bedtime_free", "wake_free"]
    assert all("?" in q["question"] for q in qs)
    assert "weekends" in qs[3]["question"]


def test_only_the_missing_half_of_a_pair_is_asked():
    q = sa.missing_fields(_routine(bedtime_free=None))
    assert q == [{"id": "sleep_free", "fields": ["bedtime_free"],
                  "question": "When do you usually go to bed on weekends and other free days?"}]
    assert sa.missing_fields(_routine(away_to=None))[0]["fields"] == ["away_to"]


def test_questions_follow_the_kinds_of_day_in_the_week():
    all_free = {d: {"am": "free", "pm": "free"} for d in care.WEEKDAYS}
    r = _routine(week=all_free, away_from=None, away_to=None, bedtime=None, wake=None)
    assert _ids(r) == []                        # no school/work days: their times are not asked
    at_home = {d: {"am": "home", "pm": "home"} for d in care.WEEKDAYS}
    r = _routine(week=at_home, away_from=None, bedtime=None, bedtime_free=None)
    assert _ids(r) == ["sleep_workdays"]        # no away and no free days


def test_the_default_week_is_asked_for_once_and_no_devices_is_missing():
    default = {d: {"am": "away", "pm": "away"} for d in care.WEEKDAYS[:5]}
    assert _ids(_routine(week=default)) == ["week"]
    assert _ids(_routine(week={})) == ["week"]  # left out means the default
    assert _ids(_routine(devices=[])) == ["devices"]


class _Msg:
    stop_reason = "end_turn"

    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]


class _Fake:
    def __init__(self, payload):
        self.calls = []
        msgs = type("M", (), {"create": lambda _s, **kw: (self.calls.append(kw), _Msg(json.dumps(payload)))[1]})()
        self.beta = type("Beta", (), {"messages": msgs})()


def test_suggest_routine_returns_the_questions_with_the_form():
    payload = {"week": {d: {"am": "away", "pm": "away"} for d in care.WEEKDAYS}, "away_from": None, "away_to": None,
               "bedtime": "23:00", "wake": "07:00", "bedtime_free": None, "wake_free": None, "devices": [], "note": ""}
    payload["week"]["sat"] = payload["week"]["sun"] = {"am": "free", "pm": "free"}
    fake = _Fake(payload)
    out = sa.suggest_routine({"model": "m", "api_key": "k"}, "School, bed at 11", client=fake)
    assert out["bedtime"] == "23:00"
    assert [q["id"] for q in out["missing"]] == ["week", "away_times", "sleep_free", "devices"]
    # the routine part is still a valid routine (the extra key is ignored when it is saved)
    assert care.clean_routine(out)["bedtime"] == "23:00"
    assert "follow-up question" in fake.calls[-1]["system"]
