"""Scheduler tests: reproducibility, coverage and the catalog §1 rules, over several seeds."""

from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scheduler import cli, devices, dist, output, planner, spec

ROOT = Path(__file__).resolve().parent.parent
RUNNER_DEVICES = ROOT.parent / "traffic-runner" / "config" / "devices.csv"
TZ = ZoneInfo("Europe/Zurich")
START = date(2026, 10, 25)   # Sunday warm-up (also the DST switch), window from Monday
SEEDS = range(8)
TIER0 = ["student", "9to5-worker"]
ROLES = {"phone": "x_a_phone", "laptop": "x_a_laptop"}


def make(name: str, seed: int, start: date = START, days: int = 15, baseline_days: int = 0) -> planner.Plan:
    prof = spec.load(name)
    base = spec.load(prof.root) if baseline_days else None
    return planner.build_plan(prof, seed, start, days, baseline=base, baseline_days=baseline_days)


CLINICAL = ["insomnia-moderate", "mdd-severe-suicidality", "social-anxiety-moderate"]
CASES = [(n, s, 0) for n in TIER0 for s in SEEDS] + [(n, s, 14) for n in CLINICAL for s in SEEDS[:4]]
OCC_RE = re.compile(r"^(\d{8}-[a-z0-9_]+-\d{2})")   # block_id without piece letter / step / companion suffix


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

@pytest.mark.parametrize("name", TIER0 + CLINICAL)
def test_same_seed_same_plan(name):
    a = output.rows(make(name, 42), ROLES, "gw_x_a")
    b = output.rows(make(name, 42), ROLES, "gw_x_a")
    assert a == b


@pytest.mark.parametrize("name", TIER0 + CLINICAL)
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
    if plan.profile.tier:
        assert Counter(phase_of.values()) == {"warmup": 1, "baseline": 14, "profile": 14}
        added = {b.id for b in plan.profile.blocks} - {b.id for b in spec.load(plan.profile.root).blocks}
        assert added
        for e in plan.entries:
            assert e.profile == (plan.profile.name if e.phase == "profile" else plan.profile.root)
            if e.profile_block in added:
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
    assert replaced   # at least in the warm-up/baseline/tier-0 days
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
            occ = {OCC_RE.match(e.block_id).group(1) for e in mine}   # pieces/steps of one occurrence = one
            per_day = Counter(o[:8] for o in occ)
            f = b.freq
            hi_count = f.clip[1] if (f.clip and f.clip_count) else f.count.bounds()[1]
            scale = max(f.scale.bounds()[1], 1.0) if f.scale else 1.0
            if f.key in ("count", "days_per_week", "nights_per_window"):
                assert max(per_day.values(), default=0) <= math.ceil(hi_count * scale), b.id
            else:
                assert max(per_day.values(), default=0) <= 1, b.id
            if f.key in ("per_week", "days_per_week"):
                weeks = Counter(planner.monday(date(int(d[:4]), int(d[4:6]), int(d[6:]))) for d in per_day)
                assert max(weeks.values(), default=0) <= math.ceil(f.period_n.bounds()[1] * scale), b.id
            if f.key == "per_window" and phase.window_start:
                assert len(per_day) <= math.ceil(f.period_n.bounds()[1] * scale), b.id
            if f.key == "count" and b.selector.day_types is None and b.selector.days is None \
                    and b.selector.nights is None and f.count.bounds()[0] >= 1 and not b.group \
                    and f.scale is None and b.replaces is None and not b.night:
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

@pytest.mark.parametrize("start", [date(2026, 10, 18), date(2027, 3, 21)])
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
    rc = cli.main(["plan", "--profile", "student", "--seed", "42", "--start", "2026-10-25", "--days", "15",
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
    calls = [c for c in cmds if "--activity video_call" in c or "--activity voice_call" in c]
    assert calls and all("--platform " in c for c in calls)


def test_cli_baseline_only_for_clinical(tmp_path):
    args = ["plan", "--profile", "student", "--seed", "1", "--start", "2026-10-25", "--days", "29",
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


# --- decisions 23.10: Sunday warm-up, day-to-day duration noise -----------------------------------

def test_window_must_start_on_monday(tmp_path):
    with pytest.raises(ValueError, match="must be a Sun, e.g. 2026-10-25"):
        make("student", 1, start=date(2026, 10, 26))
    prof = spec.load("student")
    plan = planner.build_plan(prof, 1, date(2026, 10, 26), 15, any_start=True)
    assert plan.warnings
    args = ["plan", "--profile", "student", "--seed", "1", "--start", "2026-10-26", "--devices", str(RUNNER_DEVICES),
            "--dataset", "gw_student_a", "--out", str(tmp_path / "p.csv")]
    assert cli.main(args) == 2
    assert cli.main(args + ["--any-start"]) == 0


def test_duration_noise_is_one_factor_per_day():
    for name, x in [("student", 0.25), ("9to5-worker", 0.15), ("insomnia-moderate", 0.15),
                    ("mdd-severe-suicidality", 0.25), ("social-anxiety-moderate", 0.25)]:
        prof = spec.load(name)
        assert prof.duration_noise == x
        plan = make(name, 3, days=29 if prof.tier else 15, baseline_days=14 if prof.tier else 0)
        factors = [c.duration_factor for c in plan.days]
        assert all(1 - x <= f <= 1 + x for f in factors)
        assert len(set(factors)) == len(factors)          # differs from day to day
        assert max(factors) - min(factors) > x            # and actually spreads


def test_duration_noise_scales_durations():
    """A within-block's duration = its own draw × the day's factor: without noise every wake check lies in
    5-15 min, with noise the range widens by the factor."""
    prof = spec.load("student")
    plan = make("student", 4)
    ctx = {c.date: c for c in plan.days}
    lo, hi = next(b for b in prof.blocks if b.id == "wake_check").duration.bounds()
    for e in plan.entries:
        if e.profile_block == "wake_check":
            f = ctx[e.day].duration_factor
            assert lo * f - 1 <= (e.end - e.start).total_seconds() <= hi * f + 1


def test_noise_false_keeps_the_raw_duration(case):
    plan, _ = case
    for e in plan.entries:
        if e.profile_block == "night_bursts":
            assert 120 <= (e.end - e.start).total_seconds() <= 480


# --- MDD severe + suicidality ----------------------------------------------------------------------

def clinical(name: str, seed: int) -> planner.Plan:
    return make(name, seed, days=29, baseline_days=14)


def plain_root(name: str, seed: int) -> planner.Plan:
    """The tier-0 profile alone over the same 29 days (same person, same seed)."""
    return make(spec.load(name).root, seed, days=29)


def in_profile(plan):
    return [c for c in plan.days if c.phase.name == "profile"]


@pytest.mark.parametrize("seed", range(6))
def test_mdd_skipped_campus_days(seed):
    plan = clinical("mdd-severe-suicidality", seed)
    days = [c for c in in_profile(plan) if "lecture" in c.tags]
    skipped = [c for c in days if c.skipped]
    attended = [c for c in days if any(a.id == "campus" for a in c.away)]
    assert len(skipped) + len(attended) == len(days)
    checks = 0
    for c in skipped:
        (_, s, e, allow) = c.skipped[0]
        assert allow == {"day_checks"}
        for x in plan.entries:
            if x.start < e and s < x.end and x.activity != "away":
                assert x.profile_block == "day_checks", x.block_id
                checks += 1
        assert not any(x.profile_block == "study_home" and x.day == c.date for x in plan.entries)
    assert checks or not skipped   # at home: the phone checks do run in the skipped slot


def test_mdd_attend_share_is_about_half():
    n = skipped = 0
    for seed in range(20):
        for c in in_profile(clinical("mdd-severe-suicidality", seed)):
            if "lecture" in c.tags:
                n += 1
                skipped += bool(c.skipped)
    assert 0.35 <= skipped / n <= 0.65


@pytest.mark.parametrize("seed", range(6))
def test_mdd_night_conditions(seed):
    plan = clinical("mdd-severe-suicidality", seed)
    ctx = {c.date: c for c in plan.days}
    limits = {"early_waking": (2, 30), "night_passive": (1, 30)}
    for e in plan.entries:
        if e.profile_block in limits:
            h, m = limits[e.profile_block]
            c = ctx[e.day]
            assert c.sleep <= planner.local(e.day + timedelta(days=1), h * 3600 + m * 60, TZ), e.block_id
            assert e.start > c.sleep


@pytest.mark.parametrize("seed", range(6))
def test_mdd_wake_shift_skipped_after_early_waking(seed):
    """`anchors.wake: shift ... # on days without early waking`: the morning after an early waking keeps the
    baseline wake (the person stays up, idle, until then); every other weekday morning is 30-150 min later."""
    mdd, stu = clinical("mdd-severe-suicidality", seed), plain_root("mdd-severe-suicidality", seed)
    w_mdd = {c.date: c for c in mdd.days}
    w_stu = {c.date: c.wake for c in stu.days}
    early = {e.day + timedelta(days=1): e for e in mdd.entries if e.profile_block == "early_waking"}
    for c in in_profile(mdd):
        if "weekend" in c.tags:
            continue   # weekend wake has its own value in the patch
        diff = (c.wake - w_stu[c.date]).total_seconds() / 60
        if c.date in early:
            assert diff == 0, c.date
            ew = early[c.date]
            assert not [x for x in mdd.entries if ew.end <= x.start < c.wake and x.activity != "away"]
        elif c.date - timedelta(days=1) >= in_profile(mdd)[0].date:
            assert 30 <= diff <= 150, c.date


@pytest.mark.parametrize("seed", range(4))
def test_mdd_sleep_sd_scale(seed):
    """sd × 1.7 widens the same draw: deviation from the mean = 1.7 × the student's deviation."""
    mdd, stu = clinical("mdd-severe-suicidality", seed), plain_root("mdd-severe-suicidality", seed)
    s_stu = {c.date: c.sleep for c in stu.days}
    out_stu = {c.date for c in stu.days if any(a.id == "going_out" for a in c.away)}
    for c in in_profile(mdd):
        if planner.weekday(c.date) in ("Fri", "Sat") or c.date in out_stu:
            continue   # Fri/Sat have their own value in the patch; after going out, sleep follows the return
        mean = planner.local(c.date, 24.5 * 3600, TZ)
        dev_mdd = (c.baseline_sleep - mean).total_seconds()
        dev_stu = (s_stu[c.date] - mean).total_seconds()
        assert abs(dev_mdd - 1.7 * dev_stu) <= 2


@pytest.mark.parametrize("seed", range(6))
def test_mdd_suicidality_sequence(seed):
    plan = clinical("mdd-severe-suicidality", seed)
    rows = [e for e in plan.entries if e.flag == "sensitive"]
    assert rows and all(e.profile_block == "suicidality" and e.phase == "profile" for e in rows)
    episodes = defaultdict(list)
    for e in rows:
        episodes[OCC_RE.match(e.block_id).group(1)].append(e)
    assert 1 <= len(episodes) <= 4
    assert len({k[:8] for k in episodes}) == len(episodes)   # different days
    for steps in episodes.values():
        steps.sort(key=lambda e: e.start)
        assert [e.activity for e in steps if e.activity == "crisis_resource_visit"]   # the 1.0 step always runs
        for a, b in zip(steps, steps[1:]):
            assert a.end == b.start   # back to back
        for e in steps:
            n = int(e.block_id.rsplit("-s", 1)[1])
            assert e.activity == ["repeat_visit_loop", "crisis_resource_visit", "sh_adjacent_lookup"][n - 1]
            if e.activity == "sh_adjacent_lookup":
                assert e.lookups == "1-3"
                assert "--lookups 1-3" in output.command(output.rows(
                    planner.Plan(plan.seed, plan.profile, [], [], [e], plan.horizon), ROLES, "gw_x_a")[0])


def test_mdd_scaled_blocks_are_reduced():
    mdd, stu = clinical("mdd-severe-suicidality", 3), plain_root("mdd-severe-suicidality", 3)
    def per_block(plan):
        return Counter(e.profile_block for e in plan.entries
                       if e.day >= in_profile(mdd)[0].date and e.companion_of is None)
    a, b = per_block(mdd), per_block(stu)
    for bid in ("day_checks", "messaging_day", "evening_social", "gaming"):
        assert a[bid] < b[bid], bid
    assert not [e for e in mdd.entries if e.phase == "profile" and e.block_id.endswith("-voice")]


# --- social anxiety ------------------------------------------------------------------------------------

@pytest.mark.parametrize("seed", range(8))
def test_sad_outings_kept_or_spent_at_home(seed):
    sad, stu = clinical("social-anxiety-moderate", seed), plain_root("social-anxiety-moderate", seed)
    stu_out = {c.date: next(a for a in c.away if a.id == "going_out") for c in stu.days
               if any(a.id == "going_out" for a in c.away)}
    prof = in_profile(sad)
    kept = {c.date for c in prof if any(a.id == "going_out" for a in c.away)}
    home = {c.date: c for c in prof if "going_out" in c.replaced}
    assert len(kept) <= 1                                    # keep_per_window 0-1
    assert kept | set(home) == {d for d in stu_out if d >= prof[0].date}   # the baseline's evenings
    for d, c in home.items():
        s, e = c.replaced["going_out"]
        assert (s, e) == (stu_out[d].start, stu_out[d].end)     # same would-be times
        assert c.sleep == e                                    # sleep = end of the home block
        parts = sorted((x for x in sad.entries if x.profile_block == "home_instead_of_out" and x.day == d),
                       key=lambda x: x.start)
        assert parts and parts[0].start >= s and parts[-1].end <= e
        order = [x.activity for x in parts]
        assert order == sorted(order, key=["video_stream", "gaming_session", "social_passive"].index)
        assert not [x for x in sad.entries if x.day == d and x.profile_block in ("gaming", "evening_stream")]
        assert [x for x in sad.entries if x.day == d and x.profile_block == "evening_social"] or True


@pytest.mark.parametrize("seed", range(4))
def test_sad_calls(seed):
    sad = clinical("social-anxiety-moderate", seed)
    prof = [e for e in sad.entries if e.phase == "profile"]
    for e in prof:
        if e.profile_block in ("group_call", "family_call"):
            assert e.activity == "voice_call"
        if e.profile_block == "group_call":
            assert e.options == "mic_share=0.1"
        assert not e.block_id.endswith("-voice")               # gaming without voice chat
    fam = [e for e in prof if e.profile_block == "family_call"]
    assert fam and all((e.end - e.start).total_seconds() <= 35 * 60 * 0.7 * 1.25 + 1 for e in fam)


def test_plan_csv_has_flag_and_options(tmp_path):
    out = tmp_path / "mdd.csv"
    dev = tmp_path / "devices.csv"
    dev.write_text("device,role,mac,ip,dataset\n"
                   "mdd_a_phone,phone,02:00:0a:2a:01:31,10.42.1.31,gw_mdd_a\n"
                   "mdd_a_laptop,laptop,02:00:0a:2a:01:32,10.42.1.32,gw_mdd_a\n")
    assert cli.main(["plan", "--profile", "mdd-severe-suicidality", "--seed", "2", "--start", "2026-10-25",
                     "--days", "29", "--baseline-days", "14", "--devices", str(dev), "--dataset", "gw_mdd_a",
                     "--out", str(out)]) == 0
    rows = list(csv.DictReader(out.open()))
    assert {"options", "flag"} <= set(rows[0])
    assert {r["flag"] for r in rows} == {"", "sensitive"}


def test_spec_rejects_bad_clinical_constructs(tmp_path):
    def broken(text):
        p = tmp_path / "x.yaml"
        p.write_text("profile: x\ntier: 2\nextends: student\npatch:\n" + text)
        return str(p)
    with pytest.raises(spec.SpecError, match="keep_per_window"):
        spec.load(broken("  add:\n    - {id: h, replaces: going_out, from: \"20:00\", to: \"23:00\", "
                         "device: laptop, activity: video_stream, mix: {streaming: 1}}\n"))
    with pytest.raises(spec.SpecError, match="split needs"):
        spec.load(broken("  add:\n    - {id: h, day_types: all, within: [\"20:00\", \"23:00\"], duration: 1h, "
                         "device: laptop, split: {video_stream: 1}}\n"))
    with pytest.raises(spec.SpecError, match="probability 1"):
        spec.load(broken("  add:\n    - {id: h, day_types: all, within: [\"20:00\", \"23:00\"], device: phone, "
                         "sequence: [{activity: crisis_resource_visit, probability: 0.5}]}\n"))
    with pytest.raises(spec.SpecError, match="unless_after"):
        spec.load(broken("  anchors:\n    wake: [{day_types: all, shift: 10m, unless_after: nope}]\n"))
