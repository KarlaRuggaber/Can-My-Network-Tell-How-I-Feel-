"""Observed behaviour (layer 1): quiet window, deviations from the usual range, risk flags."""

from cmn_frontend import observed as ob

BINS = ob.BINS_PER_DAY


def day(*active_ranges):
    """288 bins with True where in use; ranges as ("HH:MM", "HH:MM")."""
    a = [False] * BINS
    for s, e in active_ranges:
        sb = (int(s[:2]) * 60 + int(s[3:])) // 5
        eb = (int(e[:2]) * 60 + int(e[3:])) // 5
        for i in range(sb, eb):
            a[i] = True
    return a


def hm(minutes):
    m = int(minutes) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def test_quiet_window_is_the_night():
    prev = day(("19:00", "22:30"))
    today = day(("06:45", "07:15"), ("17:00", "20:00"))
    q = ob.quiet_window(prev, today)
    assert (hm(q["quiet_start"]), hm(q["quiet_end"])) == ("22:30", "06:45")
    assert q["quiet_start"] == -90 and round(q["quiet_hours"], 2) == 8.25


def test_brief_check_in_the_night_does_not_end_the_window():
    prev = day(("19:00", "23:00"))
    today = day(("02:00", "02:10"), ("07:00", "08:00"))
    q = ob.quiet_window(prev, today)
    assert (hm(q["quiet_start"]), hm(q["quiet_end"])) == ("23:00", "07:00")


def test_check_in_the_evening_or_morning_still_counts():
    prev = day(("19:00", "21:00"), ("23:30", "23:35"))      # going to bed: last check 23:30
    today = day(("06:05", "06:10"), ("12:00", "13:00"))     # wake check at 06:05, then away
    q = ob.quiet_window(prev, today)
    assert (hm(q["quiet_start"]), hm(q["quiet_end"])) == ("23:35", "06:05")


def test_silent_day_at_work_is_not_the_night():
    prev = day(("18:00", "23:50"))
    today = day(("00:00", "00:30"), ("05:30", "06:00"))     # silent 06:00-14:00 (work), longest gap
    q = ob.quiet_window(prev, today)
    assert (hm(q["quiet_start"]), hm(q["quiet_end"])) == ("00:30", "05:30")


def test_no_window_without_data_or_without_any_use():
    assert ob.quiet_window(None, day(("08:00", "09:00"))) is None
    assert ob.quiet_window([False] * BINS, [False] * BINS) is None


def _days(n_base, n_cur, late_cur):
    """Timeline-like days with activity: usual nights end at 23:00, late ones at 02:30."""
    days, acts = [], []
    for i in range(n_base + n_cur):
        cur = i >= n_base
        late = cur and (i - n_base) < late_cur
        bins = [0] * BINS
        for b in range(8 * 12, 23 * 12 if not late else 24 * 12):  # in use 08:00-23:00 (or to 24:00)
            bins[b] = 200
        days.append({"date": f"2026-11-{i + 1:02d}", "phase": "current" if cur else "baseline",
                     "complete": True, "packets_kept": 1000,
                     "metrics": {"C2_F3_ChatSessionCount": 10 + (i % 3), "C2_F1_UniqueSLD": 150 + i % 5,
                                 "C9_F1_CrisisLineHits": 500 if i == n_base + 1 else 0,
                                 "C9_F4_SelfHarmForumVisits": 90000 + i}})
        acts.append({"total": bins})
    # a late night needs use after midnight too: put 01:00-02:30 on the next day
    for i in range(n_base, n_base + late_cur):
        if i + 1 < len(acts):
            for b in range(12, 30):
                acts[i + 1]["total"][b] = 200
    return days, acts


def test_flags_name_a_risk_over_recent_days_not_a_single_day():
    days, acts = _days(10, 7, late_cur=4)
    base = {"C9_F1_CrisisLineHits": {"mean": 0.0, "sd": 0.0, "n": 10},
            "C9_F4_SelfHarmForumVisits": {"mean": 90000.0, "sd": 1.0, "n": 10}}
    out = ob.build(days, acts, base)
    ids = {f["id"]: f for f in out["flags"]}
    assert "later_nights" in ids and ids["later_nights"]["count"] >= 3
    assert ids["later_nights"]["text"].startswith("On ")
    assert "sensitive_sites" in ids and ids["sensitive_sites"]["sensitive"]
    assert ids["sensitive_sites"]["days"] == ["2026-11-12"]                # crisis line, not reddit
    assert "C9_F4_SelfHarmForumVisits" not in str(ids["sensitive_sites"])
    assert out["usual"]["quiet_start"]["n"] >= 3

    # one late night is not a risk
    days, acts = _days(10, 7, late_cur=1)
    assert "later_nights" not in {f["id"] for f in ob.build(days, acts, {})["flags"]}


def test_person_never_gets_sensitive_tracks_or_flags():
    days, acts = _days(10, 7, late_cur=4)
    out = ob.build(days, acts, {"C9_F1_CrisisLineHits": {"mean": 0.0, "sd": 0.0, "n": 10}})
    ob.for_person(out, days)
    assert all(not f["sensitive"] for f in out["flags"]) and all(not t["sensitive"] for t in out["tracks"])
    assert all("sensitive" not in d["observed"] for d in days)


def test_healthy_reference_compares_and_flags_from_the_first_week():
    days, acts = _days(10, 7, late_cur=4)
    healthy = {"quiet_start": [-60.0 + i for i in range(14)], "night_minutes": [0.0] * 14}
    ref = {"stats": ob.reference_stats(healthy), "n_days": 14, "people": ["Ben"]}
    out = ob.build(days, acts, {}, reference=ref)
    assert out["reference"]["people"] == ["Ben"] and "quiet_start" in out["reference"]["stats"]
    assert all("deviation_ref" in d["observed"] for d in days)
    ref_flags = [f for f in out["flags"] if f["basis"] == "reference"]
    assert any(f["id"] == "ref_later_nights" and f["title"] == "Later nights than healthy people" for f in ref_flags)
    assert "than healthy people usually do" in ref_flags[0]["phrase"]
    # too few healthy days: no reference
    assert ob.reference_stats({"quiet_start": [0.0] * 5}) == {}
    # the person gets neither the reference nor its flags
    ob.for_person(out, days)
    assert out["reference"] is None and all(f["basis"] != "reference" for f in out["flags"])
    assert all("deviation_ref" not in d["observed"] for d in days)
