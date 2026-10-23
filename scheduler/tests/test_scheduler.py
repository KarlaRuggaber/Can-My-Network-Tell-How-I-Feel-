"""Scheduler tests: reproducibility, coverage and the catalog §1 rules, over several seeds."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scheduler import cli, devices, dist, output, planner, spec

ROOT = Path(__file__).resolve().parent.parent
RUNNER_DEVICES = ROOT.parent / "traffic-runner" / "config" / "devices.csv"
TZ = ZoneInfo("Europe/Zurich")
START = date(2026, 10, 26)
SEEDS = range(8)
TIER0 = ["student", "9to5-worker"]
ROLES = {"phone": "x_a_phone", "laptop": "x_a_laptop"}


def make(name: str, seed: int, start: date = START, days: int = 15, baseline_days: int = 0) -> planner.Plan:
    prof = spec.load(name)
    base = spec.load(prof.root) if baseline_days else None
    return planner.build_plan(prof, seed, start, days, baseline=base, baseline_days=baseline_days)


CASES = [(n, s, 0) for n in TIER0 for s in SEEDS] + [("insomnia-moderate", s, 14) for s in SEEDS[:4]]


@pytest.fixture(scope="module", params=CASES, ids=lambda c: f"{c[0]}-{c[1]}")
def case(request):
    name, seed, base = request.param
    days = 15 + base
    return make(name, seed, days=days, baseline_days=base), days


def foreground(plan):
    return [e for e in plan.entries if e.activity != "away" and e.companion_of is None]


def overlap(a, b):
    return a.start < b.end and b.start < a.end


# --- reproducibility ----------------------------------------------------------------------------

@pytest.mark.parametrize("name", TIER0 + ["insomnia-moderate"])
def test_same_seed_same_plan(name):
    a = output.rows(make(name, 42), ROLES, "gw_x_a")
    b = output.rows(make(name, 42), ROLES, "gw_x_a")
    assert a == b


@pytest.mark.parametrize("name", TIER0 + ["insomnia-moderate"])
def test_different_seed_different_plan(name):
    a = output.rows(make(name, 1), ROLES, "gw_x_a")
    b = output.rows(make(name, 2), ROLES, "gw_x_a")
    assert a != b
    assert {r["start"] for r in a} != {r["start"] for r in b}


# --- coverage ------------------------------------------------------------------------------------

def test_covers_exactly_the_requested_days(case):
    plan, days = case
    want = {START + timedelta(days=i) for i in range(days)}
    assert {e.day for e in plan.entries} == want
    assert {c.date for c in plan.days} == want
    lo, hi = plan.horizon
    assert lo.astimezone(TZ).date() == START and hi.astimezone(TZ).date() == START + timedelta(days=days)
    for e in plan.entries:
        assert lo <= e.start < e.end <= hi
    # every day has a morning: the wake check
    woke = {e.day for e in plan.entries if e.profile_block == "wake_check"}
    assert woke == want


def test_phases(case):
    plan, days = case
    phase_of = {e.day: e.phase for e in plan.entries}
    assert phase_of[START] == "warmup"
    if plan.profile.name == "insomnia-moderate":
        assert Counter(phase_of.values()) == {"warmup": 1, "baseline": 14, "profile": 14}
        for e in plan.entries:
            assert e.profile == ("insomnia-moderate" if e.phase == "profile" else "9to5-worker")
            if e.profile_block in ("night_bursts", "presleep_extension"):
                assert e.phase == "profile"
    else:
        assert Counter(phase_of.values()) == {"warmup": 1, "profile": 14}


# --- catalog §1 rules ----------------------------------------------------------------------------

def test_no_overlap_on_one_device(case):
    plan, _ = case
    by_role = defaultdict(list)
    for e in foreground(plan):
        by_role[e.role].append(e)
    for role, es in by_role.items():
        es.sort(key=lambda e: e.start)
        for a, b in zip(es, es[1:]):
            assert a.end <= b.start, f"{role}: {a.block_id} overlaps {b.block_id}"


def test_calls_are_exclusive(case):
    plan, _ = case
    fg = foreground(plan)
    calls = [e for e in fg if e.exclusive]
    assert calls, "every plan has calls"
    for c in calls:
        for e in fg:
            if e is not c and overlap(c, e):
                pytest.fail(f"{e.block_id} ({e.activity}, {e.role}) runs during call {c.block_id}")
    # companions during calls: only music and the gaming session's own voice chat
    for e in plan.entries:
        if e.companion_of:
            assert e.activity in ("music_background", "voice_call")


def test_nothing_runs_while_away(case):
    plan, _ = case
    away = [e for e in plan.entries if e.activity == "away"]
    assert away
    for e in plan.entries:
        if e.activity != "away":
            for a in away:
                assert not overlap(e, a), f"{e.block_id} runs during {a.block_id}"


def test_away_replaces_evening_blocks(case):
    plan, _ = case
    evening = {b.id for p in plan.phases for b in p.profile.blocks if b.group == "evening"}
    replaced = {c.date for c in plan.days if any(a.replaces == "evening" for a in c.away)}
    assert replaced
    for e in plan.entries:
        if e.day in replaced:
            assert e.profile_block not in evening, e.block_id


def test_blocks_stay_in_their_window(case):
    plan, _ = case
    for e in plan.entries:
        if e.window:
            lo, hi = e.window
            assert lo <= e.start and e.end <= hi, e.block_id


def test_day_blocks_between_wake_and_sleep(case):
    plan, _ = case
    ctx = {c.date: c for c in plan.days}
    blocks = {(p.name, b.id): b for p in plan.phases for b in p.profile.blocks}
    for e in foreground(plan):
        b = blocks[(e.phase, e.profile_block)]
        c = ctx[e.day]
        if b.night:
            continue
        assert e.start >= c.wake, e.block_id
        if b.placement in ("fill", "within"):
            assert e.end <= c.sleep, e.block_id


def test_frequency_keys(case):
    plan, _ = case
    for phase in plan.phases:
        prof = phase.profile
        es = [e for e in foreground(plan) if e.phase == phase.name]
        for b in prof.blocks:
            mine = [e for e in es if e.profile_block == b.id]
            occ = {e.block_id.rstrip("abcdefgh") for e in mine}   # pieces of a split block = one occurrence
            per_day = Counter(o[:8] for o in occ)
            f = b.freq
            hi_count = f.clip[1] if (f.clip and f.clip_count) else f.count.bounds()[1]
            if f.key in ("count", "days_per_week", "nights_per_window"):
                assert max(per_day.values(), default=0) <= hi_count * max(f.scale, 1) + 1e-9, b.id
            else:
                assert max(per_day.values(), default=0) <= 1, b.id
            if f.key in ("per_week", "days_per_week"):
                weeks = Counter(planner.monday(date(int(d[:4]), int(d[4:6]), int(d[6:]))) for d in per_day)
                assert max(weeks.values(), default=0) <= f.period_n.bounds()[1], b.id
            if f.key == "count" and b.selector.day_types is None and b.selector.days is None \
                    and b.selector.nights is None and f.count.bounds()[0] >= 1 and not b.group:
                # an "every day" block occurs on most days (it can be dropped on away days)
                assert len(per_day) >= len(phase.dates) // 2, b.id


def test_block_ids_unique(case):
    plan, _ = case
    keys = [(e.block_id, e.role) for e in plan.entries]
    assert len(keys) == len(set(keys))
    ids = [e.block_id for e in plan.entries if e.activity != "away"]
    assert len(ids) == len(set(ids))


def test_companions_follow_their_host(case):
    plan, _ = case
    hosts = {e.block_id: e for e in plan.entries if e.companion_of is None}
    for e in plan.entries:
        if e.companion_of:
            h = hosts[e.companion_of]
            assert (h.start, h.end, h.role) == (e.start, e.end, e.role)


def test_insomnia_nights(case):
    plan, _ = case
    if plan.profile.name != "insomnia-moderate":
        pytest.skip("insomnia only")
    bursts = defaultdict(list)
    for e in plan.entries:
        if e.profile_block == "night_bursts":
            bursts[e.day].append(e)
        loc = e.start.astimezone(TZ)
        assert not (4 <= loc.hour < 5 or (loc.hour == 5 and loc.minute < 30)), f"{e.block_id} in 04:00-05:30"
    assert bursts
    ctx = {c.date: c for c in plan.days}
    for d, es in bursts.items():
        assert "symptomatic" in ctx[d].nights
        assert len(es) <= 4
        es.sort(key=lambda e: e.start)
        for a, b in zip(es, es[1:]):
            assert (b.start - a.end).total_seconds() >= 30 * 60
        for e in es:
            assert e.start >= ctx[d].sleep + timedelta(minutes=30)
            assert (e.end - e.start).total_seconds() <= 8 * 60


# --- time zone / DST ------------------------------------------------------------------------------

@pytest.mark.parametrize("start", [date(2026, 10, 19), date(2027, 3, 22)])
def test_dst_weeks(start):
    plan = make("9to5-worker", 5, start=start)
    rows = output.rows(plan, ROLES, "gw_x_a")
    offsets = {r["start"][-6:] for r in rows}
    assert offsets == {"+01:00", "+02:00"}
    for r, e in zip(rows, plan.entries):
        assert int(r["duration"]) == int((e.end - e.start).total_seconds()) > 0


# --- devices.csv ----------------------------------------------------------------------------------

def test_devices_csv(tmp_path):
    p = tmp_path / "devices.csv"
    p.write_text("# comment\ndevice,role,mac,ip,dataset\n# another\n"
                 "s_a_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_s_a\n"
                 "s_a_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_s_a\n"
                 "t_a_phone,phone,02:00:0a:2a:01:0d,10.42.1.13,gw_t_a\n")
    rows = devices.load(p)
    assert devices.map_roles(rows, "gw_s_a", ["phone", "laptop"]) == {"phone": "s_a_phone", "laptop": "s_a_laptop"}
    with pytest.raises(devices.DeviceError):
        devices.map_roles(rows, "gw_t_a", ["phone", "laptop"])
    with pytest.raises(devices.DeviceError):
        devices.map_roles(rows, "gw_nope", ["phone"])


def test_runner_devices_csv_maps_student():
    rows = devices.load(RUNNER_DEVICES)
    assert devices.map_roles(rows, "gw_student_a", ["phone", "laptop"]) == {
        "phone": "student_a_phone", "laptop": "student_a_laptop"}


# --- notation and validation ------------------------------------------------------------------------

def test_dist_notation():
    import random
    r = random.Random(1)
    assert dist.parse("06:30", dist.TIME).sample(r) == 6.5 * 3600
    assert dist.parse('"08:00"', dist.TIME).sample(r) == 8 * 3600
    assert dist.parse_duration("5-15m").bounds() == (300, 900)
    assert dist.parse_duration("1h-3h").bounds() == (3600, 10800)
    assert dist.parse("10-18", dist.NUMBER).kind == "uniform_int"
    n = dist.parse('N("06:30", 15m)', dist.TIME)
    assert n.bounds() == (6.5 * 3600 - 2700, 6.5 * 3600 + 2700)
    assert all(n.bounds()[0] <= n.sample(r) <= n.bounds()[1] for _ in range(1000))
    assert dist.parse("U(2h, 5h)", dist.DURATION).bounds() == (7200, 18000)
    assert all(2 <= dist.sample_count(r, dist.parse("Poisson(2.5)", dist.NUMBER), (2, 4)) <= 4 for _ in range(200))
    m = dist.parse_duration({"p": [.8, .2], "values": ["U(2m, 5m)", "U(5m, 8m)"]})
    assert m.bounds() == (120, 480)
    for bad in ["N(1)", "U(5, 1)", "abc", "5-1"]:
        with pytest.raises(dist.DistError):
            dist.parse(bad, dist.NUMBER)


def test_spec_rejects_mistakes(tmp_path):
    base = (ROOT / "profiles" / "student.yaml").read_text()
    for broken, msg in [
        (base.replace("activity: phone_check, duration: 5m-15m", "activity: phone_chek, duration: 5m-15m"), "unknown activity"),
        (base.replace("mix: {shopping: .7, search: .3}", "mix: {shoping: .7, search: .3}"), "unknown mix"),
        (base.replace('from: "10:00", to: "12:30"', "from: 10:00, to: 12:30"), "quote times"),
        (base.replace("device: laptop, activity: study_block}", "device: phone, activity: study_block}"), "catalog"),
    ]:
        p = tmp_path / "broken.yaml"
        p.write_text(broken)
        with pytest.raises(spec.SpecError, match=msg):
            spec.load(str(p))


def test_all_profiles_validate():
    assert cli.main(["validate"]) == 0


# --- CLI --------------------------------------------------------------------------------------------

def test_cli_writes_plan_and_commands(tmp_path):
    out = tmp_path / "plan.csv"
    rc = cli.main(["plan", "--profile", "student", "--seed", "42", "--start", "2026-10-26", "--days", "15",
                   "--devices", str(RUNNER_DEVICES), "--dataset", "gw_student_a", "--out", str(out)])
    assert rc == 0
    rows = list(csv.DictReader(out.open()))
    assert list(rows[0]) == output.PLAN_COLUMNS
    assert list(rows[0])[:8] == ["start", "end", "device", "activity_id", "domains", "profile", "seed", "block_id"]
    assert {r["device"] for r in rows} == {"student_a_phone", "student_a_laptop"}
    assert len({r["day"] for r in rows}) == 15
    cmds = [line for line in (tmp_path / "plan.commands.tsv").read_text().splitlines() if not line.startswith("#")]
    assert len(cmds) == sum(r["activity_id"] != "away" for r in rows)
    first = cmds[0].split("\t")
    assert first[4].startswith("scripts/run-activity.sh student_a_phone --activity ")
    assert "--block-id" in first[4] and "--seed 42" in first[4]


def test_cli_baseline_only_for_clinical(tmp_path):
    args = ["plan", "--profile", "student", "--seed", "1", "--start", "2026-10-26", "--days", "29",
            "--baseline-days", "14", "--devices", str(RUNNER_DEVICES), "--dataset", "gw_student_a",
            "--out", str(tmp_path / "p.csv")]
    assert cli.main(args) == 2


def test_baseline_phase_equals_plain_tier0_plan():
    """Random streams are keyed by date and block, not by phase: the baseline days of a clinical plan are the
    same schedule as the tier-0 profile run alone with the same seed (the same person)."""
    clinical = make("insomnia-moderate", 9, days=29, baseline_days=14)
    plain = make("9to5-worker", 9, days=15)
    last = START + timedelta(days=13)   # the plain plan's last night is cut at its horizon

    def key(e):
        return (e.start, e.end, e.role, e.activity, e.block_id)
    a = [key(e) for e in clinical.entries if e.day <= last]
    b = [key(e) for e in plain.entries if e.day <= last]
    assert a == b
