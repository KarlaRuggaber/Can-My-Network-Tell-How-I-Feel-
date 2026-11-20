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


# ---- times from a follow-up answer, and the note safety net ------------------------------------------

AWAY = ["away_from", "away_to"]
BED = ["bedtime", "wake"]
FREE = ["bedtime_free", "wake_free"]


def test_question_map_is_built_from_the_questions_missing_fields_asks():
    for r in (care.clean_routine({"week": {}}), _routine(bedtime_free=None), _routine(away_to=None),
              _routine(wake=None), _routine(wake_free=None)):
        for q in sa.missing_fields(r):
            if q["id"] != "week" and q["id"] != "devices":
                assert sa.TIME_QUESTIONS[q["question"]] == q["fields"]


def test_parse_times_examples():
    p = sa.parse_times
    assert p("I leave at 9:30 and I'm back at 6 p.m.", AWAY) == {"away_from": "09:30", "away_to": "18:00"}
    assert p("back around 6", AWAY[1:]) == {"away_to": "18:00"}
    assert p("bed at 11, up at 7", BED) == {"bedtime": "23:00", "wake": "07:00"}
    assert p("I sleep from half past 12 until 8", FREE) == {"bedtime_free": "00:30", "wake_free": "08:00"}
    assert p("around 7:30 to 4", AWAY) == {"away_from": "07:30", "away_to": "16:00"}
    assert p("8 and 3", AWAY) == {}             # bare numbers without a cue are ignored
    assert p("from 8 to 3", AWAY) == {"away_from": "08:00", "away_to": "15:00"}
    assert p("7.45 and 17.15", AWAY) == {"away_from": "07:45", "away_to": "17:15"}
    assert p("8h and 5 pm", AWAY) == {"away_from": "08:00", "away_to": "17:00"}
    assert p("7 o'clock, back at 5 o'clock", AWAY) == {"away_from": "07:00", "away_to": "17:00"}
    assert p("quarter to 8 and quarter past 4", AWAY) == {"away_from": "07:45", "away_to": "16:15"}
    assert p("midnight and noon", ["bedtime", "wake"]) == {"bedtime": "00:00", "wake": "12:00"}
    assert p("12 am and 11 p.m.", ["wake", "bedtime"]) == {"wake": "00:00", "bedtime": "23:00"}
    assert p("bed at 12:15, up at 9", BED) == {"bedtime": "00:15", "wake": "09:00"}
    assert p("at 9:30 and back at 9", AWAY) == {"away_from": "09:30", "away_to": "21:00"}   # not after leaving
    assert p("I'm back at 5", AWAY) == {"away_to": "17:00"}
    assert p("up at 8", BED) == {"wake": "08:00"}


def test_parse_times_ignores_what_is_not_clearly_a_time():
    for text in ("school Monday to Friday", "2 days a week", "about 3 hours a day", "Monday to Friday, 5 days",
                 "no idea", "", "I have 2 classes"):
        assert sa.parse_times(text, AWAY) == {}


def _payload(**kw):
    base = {"week": {d: {"am": "away", "pm": "away"} for d in care.WEEKDAYS}, "away_from": None, "away_to": None,
            "bedtime": "23:00", "wake": "07:00", "bedtime_free": "00:00", "wake_free": "09:00",
            "devices": [{"name": "phone", "kind": "phone", "shared": False}], "note": ""}
    base["week"]["sat"] = base["week"]["sun"] = {"am": "free", "pm": "free"}
    return {**base, **kw}


META_NOTE = (
    "User mentions being in school Mon-Wed and Thu afternoon, working Fri morning. No specific device details "
    "provided. The provided text only answers a specific question about leaving and returning times on "
    "school/work days. It does not specify the exact departure time (9:30 is likely AM) or return time "
    "(6 p.m. is PM), nor does it mention devices, bedtime, or waking times. Defaulting to 'away' for weekdays "
    "and 'free' for weekends as per instructions. Only weekend/free day times provided; weekday and away times "
    "not mentioned. The user's description contains a likely transcription error ('phone in the laptop'). "
    "Based on the context of the question asking for 'a phone, a laptop or a tablet', it is interpreted that "
    "the user possesses both a phone and a laptop. No information regarding times (bed/wake) or specific "
    "location schedules was provided.")


def test_follow_up_answer_fills_times_the_model_left_null_and_drops_the_meta_note():
    q = sa.QUESTIONS["away_times"][0]
    text = f"Question: {q}\nAnswer: I leave at 9:30 and I'm back at 6 p.m."
    fake = _Fake(_payload(note=META_NOTE))
    out = sa.suggest_routine({"model": "m", "api_key": "k"}, text, client=fake)
    assert (out["away_from"], out["away_to"]) == ("09:30", "18:00")
    assert out["note"] == ""
    assert "away_times" not in [x["id"] for x in out["missing"]]


def test_the_fallback_never_overwrites_the_model_and_only_applies_to_time_questions():
    q = sa.QUESTIONS["away_times"][0]
    out = sa.suggest_routine({"model": "m", "api_key": "k"}, f"Question: {q}\nAnswer: 9:30 and 6 p.m.",
                             client=_Fake(_payload(away_from="08:00")))
    assert (out["away_from"], out["away_to"]) == ("08:00", "18:00")
    other = f"Question: {sa.DEVICES_QUESTION}\nAnswer: a phone, bed at 11"
    out = sa.suggest_routine({"model": "m", "api_key": "k"}, other, client=_Fake(_payload()))
    assert out["away_from"] is None
    out = sa.suggest_routine({"model": "m", "api_key": "k"}, "I leave at 9:30 and I'm back at 6 p.m.",
                             client=_Fake(_payload()))
    assert out["away_from"] is None             # not a follow-up answer


def test_a_single_asked_time_goes_to_the_right_field():
    q = sa.QUESTIONS["away_times"][2]
    out = sa.suggest_routine({"model": "m", "api_key": "k"}, f"Question: {q}\nAnswer: around 6",
                             client=_Fake(_payload(away_from="07:30")))
    assert (out["away_from"], out["away_to"]) == ("07:30", "18:00")


def test_clean_note():
    assert sa.clean_note(META_NOTE) == ""
    genuine = "Every second weekend I stay with my father."
    assert sa.clean_note(genuine) == genuine
    assert sa.clean_note(f"{genuine} The user mentions school. I train on Sundays.") == f"{genuine} I train on Sundays."
    assert sa.clean_note(None) == ""
    long = " ".join(f"I visit my aunt on day {i}." for i in range(40))
    out = sa.clean_note(long)
    assert len(out) <= 300 and out.endswith(".") and out.startswith("I visit my aunt on day 0.")
