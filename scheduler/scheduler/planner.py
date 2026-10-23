"""Profile + seed -> ground-truth plan (catalog §1 rules; scheduler/README.md §4).

Steps:
1. Phases: warm-up day(s), optional baseline days (tier-0 profile), profile days.
2. Per day: tags (day types, timetable), wake, away periods, sleep, night sets, forbidden windows.
3. Per block: which days, how many occurrences (count / per_week / per_window ...), where in the day.
4. Placement: calls first (exclusive on all devices), then all other blocks in list order.
   A conflict on the same device (or with a call) pushes the block to the end of the conflict; if it no
   longer fits its window it is dropped. Fill blocks and work/study blocks are cut around conflicts instead.
5. Companions (`with: music_background`, gaming voice chat) are added next to their host.

All instants are UTC datetimes; local times are converted with zoneinfo, so DST days are handled.
Randomness: only random.Random(f"{seed}/<key>"), one stream per (day, block, ...), so changing one
block does not reshuffle the others.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import catalog
from .dist import Dist, sample_count
from .spec import WEEKDAYS, Block, Freq, Profile, TimeRef

UTC = timezone.utc
NOON = 12 * 3600
DAY = 24 * 3600
MIN_PIECE = 5 * 60          # pieces of a split block shorter than this are dropped


def rng_for(seed: int, *keys) -> random.Random:
    return random.Random("/".join([str(seed), *(str(k) for k in keys)]))


def weekday(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


# --- result types ------------------------------------------------------------------------------

@dataclass
class Phase:
    name: str                   # warmup | baseline | profile
    profile: Profile
    dates: list[date]
    window_start: date | None   # first day of the 14-day windows (None for warm-up)


@dataclass
class AwayOcc:
    id: str
    start: datetime
    end: datetime
    replaces: str | None


@dataclass
class DayCtx:
    date: date
    phase: Phase
    tags: set[str]
    timetable: dict[str, float]
    wake: datetime
    sleep: datetime
    baseline_sleep: datetime
    away: list[AwayOcc]
    nights: set[str]
    forbid: list[tuple[datetime, datetime]]


@dataclass
class Entry:
    """One plan row."""
    start: datetime
    end: datetime
    role: str
    activity: str
    block_id: str
    profile_block: str
    day: date
    phase: str
    profile: str
    mix: dict[str, float] | None = None
    pages: str | None = None
    dwell: str | None = None
    platform: str | None = None
    exclusive: bool = False
    companion_of: str | None = None
    window: tuple[datetime, datetime] | None = None   # for tests: where the block was allowed to run


@dataclass
class Plan:
    seed: int
    profile: Profile
    phases: list[Phase]
    days: list[DayCtx]
    entries: list[Entry]
    horizon: tuple[datetime, datetime]
    dropped: Counter = field(default_factory=Counter)
    warnings: list[str] = field(default_factory=list)


# --- time helpers -----------------------------------------------------------------------------

def local(d: date, secs: float, tz: ZoneInfo) -> datetime:
    """Local wall time `secs` after midnight of `d` (may be < 0 or >= 24 h) as UTC."""
    secs = int(round(secs))
    day_off, rem = divmod(secs, DAY)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    dd = d + timedelta(days=day_off)
    return datetime(dd.year, dd.month, dd.day, h, m, s, tzinfo=tz).astimezone(UTC)


def _seconds(rng: random.Random, dist: Dist) -> timedelta:
    return timedelta(seconds=round(dist.sample(rng)))


class _Resolver:
    """Resolves TimeRefs for one day."""

    def __init__(self, ctx_date: date, tz: ZoneInfo, named: dict[str, datetime | None],
                 timetable: dict[str, float]):
        self.date, self.tz, self.named, self.timetable = ctx_date, tz, named, timetable

    def __call__(self, ref: TimeRef, rng: random.Random, *, night: bool = False,
                 after: datetime | None = None) -> datetime | None:
        """`night`: times before 12:00 are on the next day. `after`: an end that is not after this
        start is on the next day (windows and periods that cross midnight)."""
        if ref.name is not None:
            if ref.name.startswith("timetable."):
                secs = self.timetable.get(ref.name.split(".", 1)[1])
                if secs is None:
                    return None
                t = local(self.date, secs, self.tz)
            else:
                t = self.named.get(ref.name)
                if t is None:
                    return None
        else:
            secs = ref.dist.sample(rng)
            if night and secs < NOON:
                secs += DAY
            t = local(self.date, secs, self.tz)
            if after is not None and t <= after:
                t = local(self.date, secs + DAY, self.tz)
        if ref.offset is not None:
            t += ref.sign * _seconds(rng, ref.offset)
        return t


# --- day contexts -------------------------------------------------------------------------------

def _timetable(prof: Profile, seed: int) -> tuple[dict[str, set[str]], dict[str, dict[str, float]]]:
    """Per weekday: extra tags and timetable values. Drawn once per seed (the same person in every phase)."""
    tags: dict[str, set[str]] = {wd: set() for wd in WEEKDAYS}
    for tag, (choose, of, other) in prof.timetable_tags.items():
        days = [wd for wd in WEEKDAYS if wd in prof.day_types[of]]
        picked = set(rng_for(seed, "timetable", "tag", tag).sample(days, min(choose, len(days))))
        for wd in days:
            if wd in picked:
                tags[wd].add(tag)
            elif other:
                tags[wd].add(other)
    values: dict[str, dict[str, float]] = {wd: {} for wd in WEEKDAYS}
    for wd in WEEKDAYS:
        wd_tags = static_tags(prof, wd, tags)
        for name, v in prof.timetable_values.items():
            dist = v
            if isinstance(v, dict):
                dist = next((x for k, x in v.items() if k in wd_tags), None)
            if dist is not None:
                values[wd][name] = dist.sample(rng_for(seed, "timetable", "value", name, wd))
    return tags, values


def static_tags(prof: Profile, wd: str, tt_tags: dict[str, set[str]]) -> set[str]:
    base = {name for name, days in prof.day_types.items() if wd in days and name not in _all_tt_tags(prof)}
    return base | tt_tags.get(wd, set()) | {wd}


def _all_tt_tags(prof: Profile) -> set[str]:
    out = set(prof.timetable_tags)
    out |= {other for _, _, other in prof.timetable_tags.values() if other}
    return out


def _night_sets(prof: Profile, seed: int, dates: list[date]) -> dict[date, set[str]]:
    """Night-set membership for every date of every calendar week that touches `dates`."""
    out: dict[date, set[str]] = {}
    weeks = sorted({monday(d) for d in dates})
    for mon in weeks:
        week = [mon + timedelta(days=i) for i in range(7)]
        for d in week:
            out.setdefault(d, set())
        for name, f in prof.night_sets.items():
            r = rng_for(seed, "nightset", name, mon.isoformat())
            n = sample_count(r, f.period_n, f.clip)
            for d in r.sample(week, min(n, 7)):
                out[d].add(name)
    return out


def _pick_days(freq: Freq, eligible, dates: list[date], r_key, seed: int,
               window_start: date | None, window_days: int) -> dict[date, int]:
    """date -> number of occurrences, for the dates of one phase."""
    out: dict[date, int] = {}
    in_phase = set(dates)

    def count_on(d: date) -> int:
        r = rng_for(seed, *r_key, "count", d.isoformat())
        n = sample_count(r, freq.count, freq.clip if freq.clip_count else None)
        if freq.scale != 1.0:   # stochastic rounding keeps the mean
            x = n * freq.scale
            n = int(x) + (1 if r.random() < x - int(x) else 0)
        return n

    if freq.key == "count":
        for d in dates:
            if eligible(d):
                out[d] = count_on(d)
        return out

    if freq.key in ("per_week", "days_per_week"):
        periods = sorted({monday(d) for d in dates})
        span = 7
    else:   # per_window, nights_per_window, keep_per_window: 14-day windows of the phase
        if window_start is None:
            return out   # warm-up days get no per-window blocks
        last = max(dates)
        periods, p = [], window_start
        while p <= last:
            periods.append(p)
            p += timedelta(days=window_days)
        span = window_days
    for p0 in periods:
        period = [p0 + timedelta(days=i) for i in range(span)]   # whole period, also days outside the plan
        cands = [d for d in period if eligible(d)]
        r = rng_for(seed, *r_key, freq.key, p0.isoformat())
        n = sample_count(r, freq.period_n, None if freq.clip_count else freq.clip)
        for d in r.sample(cands, min(n, len(cands))):
            if d in in_phase:
                out[d] = count_on(d) if freq.key in ("days_per_week", "nights_per_window") else 1
    return out


def _build_days(phase: Phase, seed: int, tz: ZoneInfo, plan: Plan) -> list[DayCtx]:
    prof = phase.profile
    tt_tags, tt_values = _timetable(prof, seed)
    nights = _night_sets(prof, seed, phase.dates) if prof.night_sets else {}

    def eligible_for(sel):
        return lambda d: sel.matches(static_tags(prof, weekday(d), tt_tags), weekday(d), nights.get(d, set()))

    away_days = {a.id: _pick_days(a.freq, eligible_for(a.selector), phase.dates, ("away", a.id), seed,
                                  phase.window_start, prof.window_days)
                 for a in prof.away}
    out = []
    for d in phase.dates:
        wd = weekday(d)
        tags = static_tags(prof, wd, tt_tags)
        ns = nights.get(d, set())
        timetable = tt_values[wd]
        res = _Resolver(d, tz, {}, timetable)

        wake = _anchor(prof.wake, tags, wd, ns, seed, d, "wake", res, night=False)
        res.named["wake"] = wake

        away: list[AwayOcc] = []
        sleep_base = None
        for a in prof.away:
            if not away_days[a.id].get(d):
                continue
            r = rng_for(seed, d.isoformat(), "away", a.id)
            start = res(a.start, r)
            if start is None:
                continue
            if a.not_before is not None:
                nb = res(a.not_before, r)
                start = max(start, nb) if nb else start
            if a.end is not None:
                end = res(a.end, r, after=start)
            elif isinstance(a.length, str):
                secs = timetable.get(a.length.split(".", 1)[1])
                end = start + timedelta(seconds=round(secs)) if secs is not None else None
            else:
                end = start + _seconds(r, a.length)
            if end is None or end <= start:
                plan.dropped[f"away {a.id}: empty"] += 1
                continue
            away.append(AwayOcc(a.id, start, end, a.replaces))
            res.named[f"away.{a.id}.start"], res.named[f"away.{a.id}.end"] = start, end
            if a.sleep_after_return is not None:
                sleep_base = end + _seconds(r, a.sleep_after_return)

        sleep = _anchor(prof.sleep, tags, wd, ns, seed, d, "sleep", res, night=True, base=sleep_base)
        baseline_sleep = _anchor(prof.sleep, tags, wd, ns, seed, d, "sleep", res, night=True, base=sleep_base,
                                 shifts=False)
        res.named.update(sleep=sleep, baseline_sleep=baseline_sleep)
        forbid = []
        for i, f in enumerate(prof.forbid):
            r = rng_for(seed, d.isoformat(), "forbid", i)
            s = res(f.start, r, night=f.night)
            e = res(f.end, r, night=f.night, after=s)
            if s and e:
                forbid.append((s, e))
        out.append(DayCtx(d, phase, tags, timetable, wake, sleep, baseline_sleep, away, ns, forbid))
    return out


def _anchor(rules, tags, wd, nights, seed, d, name, res, *, night, base=None, shifts=True) -> datetime:
    if base is None:
        rule = next((r for r in rules if r.value is not None and r.selector.matches(tags, wd, nights)), None)
        if rule is None:
            raise ValueError(f"no {name} anchor matches {d} ({wd}, {sorted(tags)})")
        secs = rule.value.sample(rng_for(seed, d.isoformat(), name))
        if night and secs < NOON:
            secs += DAY
        base = local(d, secs, res.tz)
    if shifts:
        for i, rule in enumerate(rules):
            if rule.shift is not None and rule.selector.matches(tags, wd, nights):
                base += _seconds(rng_for(seed, d.isoformat(), name, "shift", i), rule.shift)
    return base


# --- occurrences ----------------------------------------------------------------------------------

@dataclass
class _Occ:
    block: Block
    ctx: DayCtx
    start: datetime
    dur: timedelta
    lo: datetime
    hi: datetime
    n: int = 0


def _occurrences(block: Block, ctx: DayCtx, k: int, seed: int, tz: ZoneInfo, plan: Plan) -> list[_Occ]:
    if block.group == "evening" and any(a.replaces == "evening" for a in ctx.away):
        plan.dropped["evening replaced (away)"] += k
        return []
    r = rng_for(seed, ctx.date.isoformat(), "block", block.id)
    res = _Resolver(ctx.date, tz, {"wake": ctx.wake, "sleep": ctx.sleep, "baseline_sleep": ctx.baseline_sleep,
                                   **{f"away.{a.id}.{p}": getattr(a, p) for a in ctx.away for p in ("start", "end")}},
                    ctx.timetable)

    def clip(lo, hi):
        if block.not_before is not None:
            nb = res(block.not_before, r)
            if nb is not None:
                lo = max(lo, nb)
        if not block.night:
            lo, hi = max(lo, ctx.wake), min(hi, ctx.sleep)
        return lo, hi

    out: list[_Occ] = []
    if block.placement in ("at", "from_duration"):
        for _ in range(k):
            start = res(block.at, r, night=block.night)
            if start is None:
                plan.dropped[f"{block.id}: reference missing that day"] += 1
                continue
            dur = _seconds(r, block.duration)
            out.append(_Occ(block, ctx, start, dur, start, start + dur + timedelta(seconds=block.max_delay)))
    elif block.placement == "fill":
        if k:
            lo = res(block.at, r, night=block.night)
            hi = res(block.to, r, night=block.night, after=lo) if lo else None
            if lo is None or hi is None:
                plan.dropped[f"{block.id}: reference missing that day"] += 1
                return []
            lo, hi = clip(lo, hi)
            if hi - lo < timedelta(seconds=MIN_PIECE):
                plan.dropped["window too short"] += 1
                return []
            out.append(_Occ(block, ctx, lo, hi - lo, lo, hi))
    else:
        lo = res(block.within[0], r, night=block.night)
        hi = res(block.within[1], r, night=block.night, after=lo) if lo else None
        if lo is None or hi is None:
            plan.dropped[f"{block.id}: reference missing that day"] += k
            return []
        lo, hi = clip(lo, hi)
        gap = timedelta(seconds=block.min_gap)
        for _ in range(k):
            dur = _seconds(r, block.duration)
            room = (hi - lo - dur).total_seconds()
            if room < 0:
                plan.dropped["window too short"] += 1
                continue
            for _try in range(200):   # rejection sampling for min_gap
                start = lo + timedelta(seconds=round(r.uniform(0, room)))
                if all(start >= o.start + o.dur + gap or start + dur + gap <= o.start for o in out):
                    break
            else:
                plan.dropped["min_gap not satisfiable"] += 1
                continue
            out.append(_Occ(block, ctx, start, dur, lo, hi))
    out.sort(key=lambda o: o.start)
    for i, o in enumerate(out, start=1):
        o.n = i
    return out


# --- placement --------------------------------------------------------------------------------------

def _overlap(a0, a1, b0, b1) -> bool:
    return a0 < b1 and b0 < a1


class _Board:
    def __init__(self, horizon, blockers):
        self.horizon = horizon
        self.blockers = blockers      # (start, end, reason): away periods and forbidden windows
        self.placed: list[Entry] = []

    def blocked(self, s, e) -> str | None:
        if s < self.horizon[0] or e > self.horizon[1]:
            return "outside the plan"
        for b0, b1, why in self.blockers:
            if _overlap(s, e, b0, b1):
                return why
        return None

    def conflicts(self, s, e, role: str, exclusive: bool) -> list[Entry]:
        return [p for p in self.placed if _overlap(s, e, p.start, p.end)
                and (p.role == role or p.exclusive or exclusive)]

    def free_pieces(self, s, e, role, exclusive) -> list[tuple[datetime, datetime]]:
        cuts = [(p.start, p.end) for p in self.conflicts(s, e, role, exclusive)]
        cuts += [(b0, b1) for b0, b1, _ in self.blockers if _overlap(s, e, b0, b1)]
        cuts.append((datetime.min.replace(tzinfo=UTC), self.horizon[0]))
        cuts.append((self.horizon[1], datetime.max.replace(tzinfo=UTC)))
        pieces, t = [], s
        for c0, c1 in sorted(cuts):
            if c1 <= t:
                continue
            if c0 >= e:
                break
            if c0 > t:
                pieces.append((t, c0))
            t = max(t, c1)
        if t < e:
            pieces.append((t, e))
        return [(a, b) for a, b in pieces if (b - a).total_seconds() >= MIN_PIECE]


def _entry(o: _Occ, s, e, block_id, role) -> Entry:
    b, ctx = o.block, o.ctx
    return Entry(start=s, end=e, role=role, activity=b.activity, block_id=block_id, profile_block=b.id,
                 day=ctx.date, phase=ctx.phase.name, profile=ctx.phase.profile.name,
                 mix=b.mix or _default_mix(b.activity), pages=b.pages, dwell=b.dwell, platform=b.platform,
                 exclusive=b.exclusive, window=(o.lo, o.hi))


def _default_mix(activity: str) -> dict[str, float] | None:
    key = catalog.default_mix(activity)
    return {key: 1.0} if key else None


def _place(o: _Occ, board: _Board, plan: Plan) -> list[Entry]:
    b = o.block
    base_id = f"{o.ctx.date:%Y%m%d}-{b.id}-{o.n:02d}"
    if b.splittable:
        pieces = board.free_pieces(o.start, o.start + o.dur, b.device, b.exclusive)
        if not pieces:
            plan.dropped["no free time in window"] += 1
            return []
        out = []
        for i, (s, e) in enumerate(pieces):
            bid = base_id if len(pieces) == 1 else f"{base_id}{chr(ord('a') + i)}"
            out.append(_entry(o, s, e, bid, b.device))
        return out
    t = o.start
    while True:
        e = t + o.dur
        if e > o.hi:
            plan.dropped["no longer fits (overlap)"] += 1
            return []
        why = board.blocked(t, e)
        if why:
            plan.dropped[why] += 1
            return []
        c = board.conflicts(t, e, b.device, b.exclusive)
        if not c:
            return [_entry(o, t, e, base_id, b.device)]
        t = max(p.end for p in c)


def _companions(entries: list[Entry], block: Block) -> list[Entry]:
    out = []
    for host in entries:
        if block.with_:
            out.append(Entry(host.start, host.end, host.role, block.with_, f"{host.block_id}-bg", block.id,
                             host.day, host.phase, host.profile, mix={"audio": 1.0}, companion_of=host.block_id,
                             window=host.window))
        if block.activity == "gaming_session" and block.voice:
            out.append(Entry(host.start, host.end, host.role, "voice_call", f"{host.block_id}-voice", block.id,
                             host.day, host.phase, host.profile, mix={"call": 1.0},
                             platform=catalog.GAMING_VOICE_PLATFORM, exclusive=True, companion_of=host.block_id,
                             window=host.window))
    return out


# --- top level ----------------------------------------------------------------------------------------

def make_phases(profile: Profile, baseline: Profile | None, start: date, days: int,
                baseline_days: int) -> list[Phase]:
    warm = profile.warmup_days
    if days <= warm + baseline_days:
        raise ValueError(f"--days {days} leaves no profile days after {warm} warm-up and {baseline_days} baseline days")
    dates = [start + timedelta(days=i) for i in range(days)]
    first = baseline if baseline_days else profile
    phases = [Phase("warmup", first, dates[:warm], None)]
    if baseline_days:
        phases.append(Phase("baseline", baseline, dates[warm:warm + baseline_days], dates[warm]))
    rest = dates[warm + baseline_days:]
    phases.append(Phase("profile", profile, rest, rest[0]))
    return [p for p in phases if p.dates]


def build_plan(profile: Profile, seed: int, start: date, days: int, *, baseline: Profile | None = None,
               baseline_days: int = 0) -> Plan:
    if baseline_days and baseline is None:
        raise ValueError("baseline_days needs a baseline profile")
    tz = ZoneInfo(profile.timezone)
    phases = make_phases(profile, baseline, start, days, baseline_days)
    horizon = (local(start, 0, tz), local(start + timedelta(days=days), 0, tz))
    plan = Plan(seed, profile, phases, [], [], horizon)

    first_window = start + timedelta(days=profile.warmup_days)
    if weekday(first_window) != profile.start_weekday:
        plan.warnings.append(f"the first day after the warm-up ({first_window}, {weekday(first_window)}) is not a "
                             f"{profile.start_weekday}; catalog §1 starts the 14-day window on a "
                             f"{profile.start_weekday}")

    occs: list[_Occ] = []
    for phase in phases:
        ctxs = _build_days(phase, seed, tz, plan)
        plan.days.extend(ctxs)
        by_date = {c.date: c for c in ctxs}
        prof = phase.profile
        tt_tags, _ = _timetable(prof, seed)
        nights = _night_sets(prof, seed, phase.dates) if prof.night_sets else {}
        for block in prof.blocks:
            def eligible(d, sel=block.selector):
                return sel.matches(static_tags(prof, weekday(d), tt_tags), weekday(d), nights.get(d, set()))
            per_day = _pick_days(block.freq, eligible, phase.dates, ("block", block.id), seed,
                                 phase.window_start, prof.window_days)
            for d in phase.dates:
                if per_day.get(d):
                    occs.extend(_occurrences(block, by_date[d], per_day[d], seed, tz, plan))

    blockers = [(a.start, a.end, "away") for c in plan.days for a in c.away]
    blockers += [(s, e, "forbidden window") for c in plan.days for s, e in c.forbid]
    board = _Board(horizon, blockers)
    occs.sort(key=lambda o: (not o.block.exclusive, o.block.index, o.start))
    for o in occs:
        placed = _place(o, board, plan)
        board.placed.extend(placed)
        board.placed.extend(_companions(placed, o.block))

    entries = list(board.placed)
    for c in plan.days:
        for a in c.away:
            s, e = max(a.start, horizon[0]), min(a.end, horizon[1])
            if s < e:
                for role in profile.devices:
                    entries.append(Entry(s, e, role, "away", f"{c.date:%Y%m%d}-{a.id}-{role}", a.id, c.date,
                                         c.phase.name, c.phase.profile.name))
    entries.sort(key=lambda x: (x.start, x.role, x.block_id))
    plan.entries = entries
    return plan
