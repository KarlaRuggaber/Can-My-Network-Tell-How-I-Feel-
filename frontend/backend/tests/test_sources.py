"""\"Based on\": the hidden block of an answer, its stream filter, validation and the final record."""

import json

import pytest

from cmn_frontend import assistant, sources
from cmn_frontend.sources import RECORD_SEP, BasedOnSplitter

BLOCK = '<based_on>{"days": ["2025-10-31"], "metrics": ["quiet_hours"], "criteria": ["C4 Sleep"], "flags": []}</based_on>'


def ctx(person: bool = False) -> dict:
    """A small context in the shape of assistant.build_context()."""
    crit = "Sleep" if person else "C4 Sleep"
    label = "number of chat sessions" if person else "Chat sessions"
    days = [
        {"date": d, "weekday": wd, "period": "Recent", "complete": True, "packets": 1000,
         "probability_percent": {crit: L}, "parts": {crit: {label: {"value": v, "risk_degree_percent": 80, "weight_percent": 30}}}}
        for d, wd, L, v in (("2025-10-30", "Thu", 31, 3.0), ("2025-10-31", "Fri", 62, 7.0))
    ]
    c = {
        "who": "x", "areas" if person else "criteria": [crit], "days": days,
        "periods": {"Recent": {"results": {crit: {"present": True, "days_at_or_above_threshold": 3}}}},
        "baseline_mean_sd_of_metrics": {label: {"mean": 4.0, "sd": 1.5, "n": 20}},
        "observed_behaviour": {
            "usual": {"quiet_hours": {"mean": 7.2, "sd": 0.4}, "quiet_start": {"mean": -50.0, "sd": 30.0}},
            "flags": [{"id": "later_nights", "title": "Later nights", "days": ["2025-10-30", "2025-10-31"], "count": 2,
                       "of_last": 7}],
            "days": {
                "2025-10-30": {"went_quiet": "23:10", "quiet_hours": 6.9},
                "2025-10-31": {"went_quiet": "00:20", "quiet_hours": 5.2},
            },
        },
    }
    if not person:
        c["unscored_criteria"] = {"criteria": ["C9 Suicidality"], "days": {}}
    return c


def record(hidden, person=False, focus=None):
    return sources.sources_record(hidden, ctx(person), person, focus)


# ---- stream filter ----

def feed(chunks):
    sp = BasedOnSplitter()
    text = "".join(sp.feed(c) for c in chunks) + sp.finish()
    return text, sp.hidden


ANSWER = "Your devices went quiet later on Friday.\n\n" + BLOCK


@pytest.mark.parametrize("cut", range(1, len(ANSWER)))
def test_block_is_held_back_on_any_split(cut):
    text, hidden = feed([ANSWER[:cut], ANSWER[cut:]])
    assert text == "Your devices went quiet later on Friday."
    assert hidden == BLOCK


def test_block_one_character_at_a_time():
    assert feed(list(ANSWER)) == ("Your devices went quiet later on Friday.", BLOCK)


def test_no_block_is_all_visible_and_hidden_is_none():
    assert feed(["Fine ", "answer ", "with a < sign and <b>bold</b>."]) == (
        "Fine answer with a < sign and <b>bold</b>.", None)
    assert feed(["ends with a partial tag <based"]) == ("ends with a partial tag <based", None)


def test_block_without_closing_tag_is_still_held_back_and_parsed():
    text, hidden = feed(["Answer.\n", '<based_on>{"days": ["2025-10-31"], "metrics": [], "criteria": [], "flags": []}'])
    assert text == "Answer."
    assert sources.parse_block(hidden)["days"] == ["2025-10-31"]


def test_parse_block_tolerates_fences_and_rejects_garbage():
    fenced = '<based_on>```json\n{"days": ["2025-10-31"]}\n```</based_on>'
    assert sources.parse_block(fenced) == {"days": ["2025-10-31"], "metrics": [], "criteria": [], "flags": []}
    assert sources.parse_block("<based_on>not json</based_on>") is None
    assert sources.parse_block("<based_on>[1, 2]</based_on>") is None
    assert sources.parse_block(None) is None


# ---- validation and enrichment ----

def test_valid_block_is_enriched_from_the_context():
    r = record(BLOCK)
    assert r["fallback"] is False and r["no_data"] is False
    by = {(i["kind"], i["id"]): i for i in r["items"]}
    q = by[("metric", "quiet_hours")]
    assert q["name"] == "Quiet window" and q["unit"] == "h" and q["icon"] == "moon"
    assert q["values"] == [{"day": "2025-10-31", "text": "5.2 h"}] and q["usual"] == "6.8 to 7.6 h"
    c = by[("criterion", "C4")]
    assert c["name"] == "Sleep (C4)" and c["code"] == "C4" and c["values"] == [{"day": "2025-10-31", "text": "probability 62 %"}]
    assert "Recent: present" in c["detail"]
    d = by[("day", "2025-10-31")]
    assert d["detail"] == "Fri, Recent"
    assert [i["kind"] for i in r["items"]] == ["metric", "criterion", "day"]


def test_values_come_from_data_not_from_the_model():
    block = '<based_on>{"days": [], "metrics": ["quiet_hours"], "value": 99, "criteria": [], "flags": []}</based_on>'
    r = record(block)
    assert r["items"][0]["values"] == [{"day": "2025-10-31", "text": "5.2 h"}]      # latest day with a value
    assert "99" not in json.dumps(r)


def test_unknown_entries_are_dropped():
    block = ('<based_on>{"days": ["2025-10-31", "2024-01-01"], "metrics": ["quiet_hours", "made_up"], '
             '"criteria": ["C4 Sleep", "C2 Nothing"], "flags": ["later_nights", "nope"]}</based_on>')
    r = record(block)
    ids = {(i["kind"], i["id"]) for i in r["items"]}
    assert ids == {("metric", "quiet_hours"), ("criterion", "C4"), ("flag", "later_nights"), ("day", "2025-10-31")}
    assert sources.listed_unknown(block, ctx(), False) == {"valid": True, "unknown": 4, "listed": 8, "codes": []}


def test_scored_metrics_flags_and_a_bare_code():
    block = '<based_on>{"days": ["2025-10-31"], "metrics": ["Chat sessions"], "criteria": ["C4"], "flags": ["later_nights"]}</based_on>'
    by = {i["kind"]: i for i in record(block)["items"]}
    m = by["metric"]
    assert m["name"] == "Chat sessions" and m["values"] == [{"day": "2025-10-31", "text": "7"}]
    assert m["usual"] == "2.5 to 5.5" and m["detail"] == "risk degree 80 %, weight 30 %"
    assert by["criterion"]["id"] == "C4"
    assert by["flag"]["detail"] == "2 of the last 7 days" and by["flag"]["days"] == ["2025-10-30", "2025-10-31"]


def test_clock_metric_uses_clock_times():
    r = record('<based_on>{"days": ["2025-10-30"], "metrics": ["went_quiet"]}</based_on>')
    m = r["items"][0]
    assert m["name"] == "Went quiet" and m["values"] == [{"day": "2025-10-30", "text": "23:10"}]
    assert m["usual"] == "22:40 to 23:40"        # mean -50 min +/- 30 min = 22:40 to 23:40


def test_person_view_has_area_names_and_no_codes_or_scores():
    block = ('<based_on>{"days": ["2025-10-31"], "metrics": ["number of chat sessions", "quiet_hours"], '
             '"criteria": ["Sleep", "C4", "C9"], "flags": []}</based_on>')
    r = record(block, person=True)
    crit = [i for i in r["items"] if i["kind"] == "criterion"]
    assert [(i["name"], i["code"], i["values"]) for i in crit] == [("Sleep", None, [])]
    text = json.dumps(r)
    assert "C4" not in text and "C9" not in text and "L 0." not in text
    assert any(i["name"] == "Number of chat sessions" for i in r["items"])
    assert sources.listed_unknown(block, ctx(True), True)["codes"] == []
    # the clinician view of the same names would carry the code
    assert "C4" in json.dumps(record(BLOCK))


def test_criterion_without_scores_clinician():
    r = record('<based_on>{"criteria": ["C9 Suicidality"]}</based_on>')
    c = r["items"][0]
    assert c["code"] == "C9" and c["values"] == [] and c["name"] == "Suicidality (C9)"


# ---- fallback and no data ----

@pytest.mark.parametrize("hidden", [None, "<based_on>oops</based_on>", "<based_on>[]</based_on>",
                                    '<based_on>{"days": ["1999-01-01"], "metrics": ["zzz"]}</based_on>'])
def test_missing_invalid_or_unusable_block_falls_back_to_the_focus(hidden):
    r = record(hidden, focus="timeline, day 2025-10-30, C4")
    assert r["fallback"] is True and r["no_data"] is False
    assert [(i["kind"], i["id"]) for i in r["items"]] == [("criterion", "C4"), ("day", "2025-10-30")]


def test_fallback_without_a_matching_focus_is_empty_and_flag_focus_works():
    assert record(None, focus="care plan") == {"items": [], "fallback": True, "no_data": False}
    r = record(None, focus="flag later_nights")
    assert r["fallback"] is True and [i["id"] for i in r["items"]] == ["later_nights"]
    person = record(None, person=True, focus="day 2025-10-31, C4")
    assert [(i["name"], i["code"]) for i in person["items"]] == [("Sleep", None), ("2025-10-31", None)]


def test_an_empty_block_means_no_data_of_this_person():
    r = record('<based_on>{"days": [], "metrics": [], "criteria": [], "flags": []}</based_on>')
    assert r == {"items": [], "fallback": False, "no_data": True}


# ---- the stream: text, then one record ----

def test_answer_stream_text_then_one_record():
    out = "".join(sources.answer_stream(iter(["Quiet on ", "Friday.\n\n", BLOCK[:20], BLOCK[20:]]), ctx(), False))
    text, rec = out.split(RECORD_SEP)
    assert text == "Quiet on Friday."
    r = json.loads(rec)
    assert r["fallback"] is False and {i["kind"] for i in r["items"]} == {"metric", "criterion", "day"}


def test_answer_stream_without_a_block_still_ends_with_a_record():
    text, rec = "".join(sources.answer_stream(iter(["Plain."]), ctx(), False, "day 2025-10-31")).split(RECORD_SEP)
    assert text == "Plain." and json.loads(rec)["fallback"] is True


def test_the_safety_net_runs_on_the_visible_text_only():
    raw = "Your nights were later. That looks like insomnia. Talk to your care team.\n\n" + BLOCK.replace("C4 Sleep", "Sleep")
    out = "".join(sources.answer_stream(list(raw), ctx(True), True, guard=assistant.guard_person))
    text, rec = out.split(RECORD_SEP)
    assert "insomnia" not in text and assistant.PERSON_REPLACEMENT in text and "based_on" not in text
    items = json.loads(rec)["items"]
    assert items and all("C4" not in json.dumps(i) for i in items)


def test_prompt_asks_for_the_block_in_both_views():
    for person in (True, False):
        p = " ".join(assistant.system_blocks({}, person)[0]["text"].split())
        assert '<based_on>{"days": [], "metrics": [], "criteria": [], "flags": []}</based_on>' in p
        assert "end EVERY answer" in p and "copied character for character from <results>" in p


# ---- eval: the block is checked, never counted as answer text ----

def _eval_records(answer: str, person: bool):
    from eval import assistant_eval as ev
    from test_assistant_rules import FakeClaude
    system = assistant.system_blocks(ctx(person), person)
    case = ev.Case("s1", "person" if person else "clinician", ev.BEN if person else ev.MARIA, ("How was Friday?",))
    return ev.run_case(case, {"system": system}, {"api_key": "x", "model": "m"}, client=FakeClaude([answer]))


def test_eval_checks_the_block_and_strips_it_from_the_answer():
    recs = _eval_records("Devices went quiet at 00:20 on Friday.\n\n" + BLOCK, person=False)
    r = recs[0]
    assert r["answer"] == "Devices went quiet at 00:20 on Friday." and "based_on" not in r["answer"]
    assert r["checks"]["sources"] is True and r["checks"]["sources_known"] is True
    assert r["checks"]["sources_codes"] is None                         # clinician: codes are fine
    from eval import assistant_eval as ev
    assert not ev.failed_checks(r)


def test_eval_flags_missing_blocks_unknown_entries_and_codes_in_person_answers():
    from eval import assistant_eval as ev
    none = _eval_records("Devices went quiet late on Friday.", person=False)[0]
    assert none["checks"]["sources"] is False and none["checks"]["sources_known"] is None
    assert ev.failed_checks(none) == ["sources"]
    bad = _eval_records('Late.\n<based_on>{"days": ["2025-10-31", "2020-01-01"], "metrics": ["bogus"]}</based_on>', person=False)[0]
    assert bad["checks"]["sources"] is True and bad["checks"]["sources_known"] is False
    assert bad["issues"]["sources_known"] == ["2 of 3 entries not in the context"]
    ok = _eval_records('Late.\n<based_on>{"days": ["2025-10-31"], "criteria": ["Sleep"]}</based_on>', person=True)[0]
    assert ok["checks"]["sources"] and ok["checks"]["sources_codes"] is True
