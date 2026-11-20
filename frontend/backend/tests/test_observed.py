"""Observed behaviour (layer 1): quiet window, deviations from the usual range, risk and change flags,
the typical (reference-group) range from pooled days or published norms."""

import json
import math

import pytest

from cmn_frontend import norms
from cmn_frontend import observed as ob
from cmn_frontend.profiles import attention_summary

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


ICONS = {"moon", "sunrise", "clock", "night-use", "chat", "globe", "alert", "irregular", "change", "note",
         "explain", "away", "phone", "laptop", "person", "data", "lock"}


def _check_flags(flags):
    for f in flags:
        assert f["kind"] in ("risk", "change") and f["icon"] in ICONS, f
        assert "healthy" not in (f["title"] + f["text"] + f["phrase"]).lower()


def test_typical_reference_compares_and_flags_from_the_first_week():
    days, acts = _days(10, 7, late_cur=4)
    typical = {"quiet_start": [-60.0 + i for i in range(14)], "night_minutes": [0.0] * 14}
    out = ob.build(days, acts, {}, reference={"values": typical, "n_days": 14, "people": ["Ben"]})
    ref = out["reference"]
    assert ref["source"] == "pooled" and ref["people"] == ["Ben"] and "quiet_start" in ref["stats"]
    assert ref["label"].startswith("typical") and "_pct" not in ref
    json.dumps(out)                                                        # no functions leak out
    assert set(ref["tracks"]["quiet_start"]) == {"p16", "p50", "p84", "n"}
    assert all("deviation_ref" in d["observed"] and "percentile_ref" in d["observed"] for d in days)
    ref_flags = [f for f in out["flags"] if f["basis"] == "reference"]
    assert any(f["id"] == "ref_later_nights" and f["title"] == "Later nights than typical" for f in ref_flags)
    assert "than is typical for the reference group" in ref_flags[0]["phrase"]
    _check_flags(out["flags"])
    # 10 minutes of use at night against a reference of zeros is no clear difference (SD floor)
    nd, na = _nights([0] + [10] * 12)
    few = ob.build(nd, na, {}, reference={"values": {"night_minutes": [0.0] * 14}})
    late = [d for d in nd if d["observed"]["night_minutes"]]
    assert late and all(d["observed"]["percentile_ref"]["night_minutes"] == 100.0 for d in late)
    assert all(0 < d["observed"]["deviation_ref"]["night_minutes"] == round(10 / 15, 2) for d in late)
    assert "ref_night_use" not in {f["id"] for f in few["flags"]}
    # too few typical days: no reference
    assert ob.reference_stats({"quiet_start": [0.0] * 5}) == {}
    assert ob.pooled_reference({"quiet_start": [0.0] * 5}) is None
    # the person gets neither the reference nor its flags
    ob.for_person(out, days)
    assert out["reference"] is None and all(f["basis"] != "reference" for f in out["flags"])
    assert all("deviation_ref" not in d["observed"] and "percentile_ref" not in d["observed"] for d in days)


def test_pooled_reference_uses_empirical_percentiles():
    vals = [float(v) for v in range(1, 101)]                     # 1..100 minutes of use at night
    ref = ob.pooled_reference({"night_minutes": vals}, n_days=100, people=["A", "B"])
    t = ref["tracks"]["night_minutes"]
    assert (t["p16"], t["p50"], t["p84"], t["n"]) == (16.84, 50.5, 84.16, 100)
    assert ref["normal_assumption"] is False
    pct = ref["_pct"]["night_minutes"]
    assert pct(50.0) == 49.5 and pct(0.0) == 0.0 and pct(1000.0) == 100.0
    # skewed values: the empirical median, not the mean
    skew = ob.pooled_reference({"online_hours": [1.0] * 10 + [10.0] * 2})
    assert skew["tracks"]["online_hours"]["p50"] == 1.0 and skew["stats"]["online_hours"]["mean"] == 2.5
    # percentile -> z, clipped
    assert ob.percentile_z(50.0) == 0 and round(ob.percentile_z(84.13), 2) == 1.0
    assert math.isfinite(ob.percentile_z(100.0)) and ob.percentile_z(100.0) > 3


def test_normal_assumption_percentiles():
    assert norms.normal_percentile(7.5, 7.5, 1.4) == 50.0
    assert round(norms.normal_percentile(8.9, 7.5, 1.4), 2) == 84.13
    assert round(norms.normal_quantile(16, 0, 1), 3) == -0.994
    mix = norms.Mixture([(1, 7.0, 1.0)])
    assert abs(mix.quantile(84.134) - 8.0) < 1e-3
    two = norms.Mixture([(1, 6.0, 1.0), (1, 8.0, 1.0)])
    assert abs(two.quantile(50) - 7.0) < 1e-6 and abs(two.sd - math.sqrt(2)) < 1e-9
    # old-style {"stats"} reference: P16/P84 = mean -/+ SD
    out = ob.build(*_days(10, 7, late_cur=0), {}, reference={"stats": {"quiet_start": {"mean": -60.0, "sd": 30.0, "n": 20}}})
    t = out["reference"]["tracks"]["quiet_start"]
    assert (round(t["p16"]), t["p50"], round(t["p84"])) == (-90, -60.0, -30) and out["reference"]["normal_assumption"]


def test_norms_file_is_complete_and_cited():
    data = norms.load()
    for e in data["entries"]:
        src = data["sources"][e["source"]]
        assert src["citation"] and src["population"] and src["url"].startswith("https://")
        assert e["location"] and e["proxy_note"] and e["stat"] in ("mean_sd", "mean_sd_by_age", "median", "mean", "pooled_mean")
        assert e["track"] is None or e["track"] in ob.TRACK_BY_KEY
    by_id = {e["id"]: e for e in data["entries"]}
    rows = {r["age"]: r for r in by_id["maslowsky2014_duration_by_age"]["rows"]}
    assert (rows[13]["mean"], rows[18]["mean"], rows[22]["mean"], rows[32]["mean"]) == (8.5, 7.3, 8.5, 7.7)
    assert by_id["galland2018_onset"]["values"]["all"] == -33             # 23:27, Table 4
    assert by_id["galland2018_offset"]["values"]["free"] == 8 * 60 + 47   # 8:47, Table 5


def test_external_reference_by_age_band():
    ref = norms.external_reference("15-18")
    assert ref["source"] == "external" and ref["normal_assumption"] and ref["age_band"] == "15-18"
    q = ref["tracks"]["quiet_hours"]                       # Add Health, ages 15-18, mixture of normals
    assert 7.3 < q["p50"] < 8.0 and q["p16"] < q["p50"] < q["p84"]
    assert q["n"] == 3888 + 4858 + 5288 + 5101 and "Maslowsky" in q["citation"] and q["proxy_note"]
    o = ref["tracks"]["online_hours"]                      # ABCD passive sensing, mean +- SD
    assert o["p50"] == pytest.approx(4.967) and o["p16"] == pytest.approx(4.967 - 0.9945 * 2.9, abs=1e-3)
    # a centre without a spread is a point, never a range
    assert "quiet_start" not in ref["tracks"] and ref["points"]["quiet_start"][0]["values"]["school"] == -60
    assert {p["stat"] for p in ref["points"]["online_hours"]} == {"median"}          # JAMES 2024
    assert "quiet_start_sd7" not in ref["points"]                                  # adult norm only
    assert any("SRI" in c["unit"] for c in ref["context"])
    adult = norms.external_reference("19-24")
    assert "quiet_start_sd7" in adult["points"] and "online_hours" not in adult["tracks"]
    assert adult["tracks"]["quiet_hours"]["p50"] > q["p50"]                        # 19-24: longer sleep


def test_external_reference_in_build():
    days, acts = _days(10, 7, late_cur=4)
    out = ob.build(days, acts, {}, reference=norms.external_reference("15-18"))
    ref = out["reference"]
    assert ref["source"] == "external" and "_pct" not in ref and ref["tracks"]["quiet_hours"]["citation"]
    json.dumps(out)
    d = next(x["observed"] for x in days if x["observed"]["quiet_hours"] is not None)
    assert 0 <= d["percentile_ref"]["quiet_hours"] <= 100
    assert d["percentile_ref"]["quiet_start"] is None and d["deviation_ref"]["quiet_start"] is None
    # an 8 h quiet window lies inside the typical range of 15-18-year-olds
    q = ref["tracks"]["quiet_hours"]
    eight = [x for x in days if x["observed"]["quiet_hours"] and q["p16"] <= x["observed"]["quiet_hours"] <= q["p84"]]
    assert eight and all(16 <= x["observed"]["percentile_ref"]["quiet_hours"] <= 84 for x in eight)
    _check_flags(out["flags"])


def _nights(quiet_starts):
    """Days in use from 08:00 until the went-quiet time (minutes from midnight, negative = evening)."""
    n = len(quiet_starts)
    acts = [[0] * BINS for _ in range(n)]
    for i, q in enumerate(quiet_starts):
        if i == 0:
            continue
        for b in range(8 * 12, BINS):                       # day i-1: in use from 08:00 ...
            if b * 5 < 24 * 60 + min(q, 0):
                acts[i - 1][b] = 200
        for b in range(0, max(q, 0) // 5):                  # ... and after midnight on day i
            acts[i][b] = 200
    for b in range(8 * 12, 22 * 12):
        acts[-1][b] = acts[-1][b] or 200
    days = [{"date": f"2026-10-{i + 1:02d}", "phase": "baseline" if i < n - 8 else "current",
             "complete": i < n - 1, "packets_kept": 1000, "metrics": {}} for i in range(n)]
    return days, [{"total": a} for a in acts]


def test_irregular_nights_against_the_baseline_rolling_sd():
    base = [-60, -55, -65] * 6                                 # 23:00 +- 5 min, 18 nights
    cur = [-150, 90, -150, 90, -150, 90, -150, 90]             # 21:30 / 01:30 alternating
    days, acts = _nights([0] + base + cur)
    out = ob.build(days, acts, {})
    obs = [d["observed"] for d in days]
    assert [o["quiet_start"] for o in obs[1:6]] == [-60, -55, -65, -60, -55]
    assert obs[3]["quiet_start_sd7"] is None and obs[4]["quiet_start_sd7"] == pytest.approx(4.08, abs=0.01)
    assert out["usual"]["quiet_start_sd7"]["mean"] < 6
    ids = {f["id"]: f for f in out["flags"]}
    f = ids["irregular_nights"]
    assert f["kind"] == "risk" and f["icon"] == "irregular" and f["track"] == "quiet_start_sd7"
    assert f["text"].endswith("went quiet at more irregular times than usual.")
    assert "change_irregular_nights" not in ids
    assert next(t for t in out["tracks"] if t["key"] == "quiet_start_sd7")["risk"] == [1]
    # an away period does not count as a night
    away = {d["date"]: "away_period" for d in days[-8:]}
    out2 = ob.build(*_nights([0] + base + cur), {}, day_types=away)
    assert "irregular_nights" not in {f["id"] for f in out2["flags"]}
    _check_flags(out["flags"])


def test_change_flags_in_the_improving_direction():
    base = [60, 55, 65] * 6                                    # usually quiet around 01:00
    cur = [-120] * 8                                           # now 22:00 every night
    days, acts = _nights([0] + base + cur)
    out = ob.build(days, acts, {})
    ids = {f["id"]: f for f in out["flags"]}
    assert "later_nights" not in ids
    c = ids["change_later_nights"]
    assert c["kind"] == "change" and c["icon"] == "change" and c["direction"] == -1 and c["basis"] == "own"
    assert c["title"] == "Earlier nights" and "to discuss" in c["text"] and not c["sensitive"]
    # risks in both directions have no change flag; the care plan can switch change flags off
    assert not any(f["id"].startswith("change_") and f["track"] == "online_hours" for f in out["flags"])
    days, acts = _nights([0] + base + cur)
    assert not [f for f in ob.build(days, acts, {}, changes=False)["flags"] if f["kind"] == "change"]
    _check_flags(out["flags"])


def test_attention_counts_open_risk_flags():
    flags = [{"id": "later_nights", "kind": "risk", "days": ["2026-11-10", "2026-11-12"], "sensitive": False},
             {"id": "change_fewer_chats", "kind": "change", "days": ["2026-11-12"], "sensitive": False},
             {"id": "sensitive_sites", "kind": "risk", "days": ["2026-11-11"], "sensitive": True}]
    assert attention_summary(flags) == {"flags": 2, "alert": True}
    seen = {"sensitive_sites": {"last_day": "2026-11-11"}, "later_nights": {"last_day": "2026-11-11"}}
    assert attention_summary(flags, seen) == {"flags": 1, "alert": False}   # later_nights has a new day
    assert attention_summary([]) == {"flags": 0, "alert": False}


def test_api_attention_and_reference_switch(tmp_path):
    from fastapi.testclient import TestClient

    from cmn_frontend import auth
    from cmn_frontend.api import create_app
    from cmn_frontend.export import export_dataset
    from cmn_frontend.profiles import Device, Profile, ProfileStore
    from fixtures import DS, PHONE_IP, make_run

    s = make_run(tmp_path)
    export_dataset(DS, s)
    ProfileStore(s).upsert(Profile("tester", "Tester", DS, devices=[Device(PHONE_IP, "phone")]))
    users = auth.UserStore(s.home_dir)
    users.add("doc", "pw-doc", "multi", ["*"])
    users.add("anna", "pw-anna", "single", ["tester"])

    def client(user, pw):
        c = TestClient(create_app(s))
        assert c.post("/api/login", json={"username": user, "password": pw}).status_code == 200
        return c

    doc = client("doc", "pw-doc")
    [item] = doc.get("/api/profiles").json()
    assert set(item["attention"]) == {"flags", "alert"} and isinstance(item["attention"]["flags"], int)
    pooled = doc.get("/api/profiles/tester").json()
    ext = doc.get("/api/profiles/tester?reference=external&age_band=19-24").json()
    assert pooled["observed"]["reference"] is None          # nobody else to pool from
    r = ext["observed"]["reference"]
    assert r["source"] == "external" and r["age_band"] == "19-24" and r["available"] == ["pooled", "external"]
    assert "quiet_hours" in r["tracks"] and all("percentile_ref" in d["observed"] for d in ext["days"])
    assert ext["gate"] == pooled["gate"]                    # the reference never touches the gate
    assert doc.get("/api/profiles/tester?reference=healthy").status_code == 400
    assert doc.get("/api/profiles/tester?age_band=3-5").status_code == 400
    anna = client("anna", "pw-anna")
    assert "attention" not in anna.get("/api/profiles").json()[0]
    me = anna.get("/api/profiles/tester?reference=external").json()
    assert me["observed"]["reference"] is None and all("percentile_ref" not in d["observed"] for d in me["days"])
