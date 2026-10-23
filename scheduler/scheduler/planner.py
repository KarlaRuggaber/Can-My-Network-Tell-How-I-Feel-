"""Profile + seed -> ground-truth plan (catalog §1 rules; scheduler/README.md §4).

Steps:
1. Phases: warm-up day(s), optional baseline days (tier-0 profile), profile days.
2. Per day: tags (day types, timetable), wake, away periods, sleep, night sets, forbidden windows.
   Clinical extras: attend_share (skipped periods), keep_per_window (kept / replaced periods),
   sd_scale and unless_after on anchors (the latter needs a second pass over the days).
3. Per block: which days, how many occurrences (count / per_week / per_window ..., `scale`, `only_if`,
   `replaces`, `cancels`), where in the day.
4. Placement: calls first (exclusive on all devices), then all other blocks in list order.
   A conflict on the same device (or with a call) pushes the block to the end of the conflict; if it no
   longer fits its window it is dropped. Fill blocks and work/study blocks are cut around conflicts instead.
   `split` blocks are cut into consecutive parts by share, `sequence` blocks run their steps back to back.
5. Companions (`with: music_background`, gaming voice chat) are added next to their host.

All instants are UTC datetimes; local times are converted with zoneinfo, so DST days are handled.
Randomness: only random.Random(f"{seed}/<key>"), one stream per (day, block, ...), so changing one
block does not reshuffle the others.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import catalog
from .dist import Dist, sample_count
from .spec import WEEKDAYS, Block, Freq, Profile, Step, TimeRef

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
    duration_factor: float = 1.0
    replaced: dict[str, tuple[datetime, datetime]] = field(default_factory=dict)   # away id -> its would-be period
    skipped: list[tuple[str, datetime, datetime, frozenset[str]]] = field(default_factory=list)   # attend_share


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
    lookups: str | None = None
    platform: str | None = None
    exclusive: bool = False
    companion_of: str | None = None
    options: str | None = None
    flag: str | None = None
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


def _sround(x: float, r: random.Random) -> int:
    """Stochastic rounding: 3.4 -> 3 with 60 %, 4 with 40 % (keeps the mean of scaled counts)."""
    n = int(x)
    return n + (1 if r.random() < x - n else 0)


def instance_factor(seed: int, kind: str, block_id: str, dist: Dist | None) -> float:
    """A factor drawn once per seed (instance), e.g. `scale: 'U(0.6, 0.7)'`: the same in every window."""
    return dist.sample(rng_for(seed, "instance", kind, block_id)) if dist is not None else 1.0


def _windows(phase: Phase, window_days: int) -> list[tuple[date, list[date]]]:
    """The 14-day windows of a phase as (first day, days incl. those after the plan end)."""
    if phase.window_start is None:
        return []
    out, p, last = [], phase.window_start, max(phase.dates)
    while p <= last:
        out.append((p, [p + timedelta(days=i) for i in range(window_days)]))
        p += timedelta(days=window_days)
    return out


def _pick_days(freq: Freq, eligible, phase: Phase, r_key, seed: int, window_days: int,
               scale: float = 1.0) -> dict[date, int]:
    """date -> number of occurrences, for the dates of one phase."""
    out: dict[date, int] = {}
    dates = phase.dates
    in_phase = set(dates)

    def count_on(d: date) -> int:
        r = rng_for(seed, *r_key, "count", d.isoformat())
        n = sample_count(r, freq.count, freq.clip if freq.clip_count else None)
        return _sround(n * scale, r) if scale != 1.0 else n

    if freq.key == "count":
        for d in dates:
            if eligible(d):
                out[d] = count_on(d)
        return out

    if freq.key in ("per_week", "days_per_week"):
        periods = [(mon, [mon + timedelta(days=i) for i in range(7)]) for mon in sorted({monday(d) for d in dates})]
    else:   # per_window, nights_per_window; warm-up days get none
        periods = _windows(phase, window_days)
    for p0, period in periods:   # whole period, also days outside the plan (partial periods get a pro-rated share)
        cands = [d for d in period if eligible(d)]
        r = rng_for(seed, *r_key, freq.key, p0.isoformat())
        n = sample_count(r, freq.period_n, None if freq.clip_count else freq.clip)
        if scale != 1.0 and freq.key in ("per_week", "per_window"):
            n = _sround(n * scale, r)
        for d in r.sample(cands, min(n, len(cands))):
            if d in in_phase:
                out[d] = count_on(d) if freq.key in ("days_per_week", "nights_per_window") else 1
    return out


def _away_days(prof: Profile, phase: Phase, seed: int, eligible_for) -> tuple[dict[str, set], dict[str, set]]:
    """Per away period: the days it happens, and the days it was drawn but not kept (keep_per_window).
    The draw uses the same random streams as the tier-0 profile, so the replaced days are exactly the days
    the baseline person would have been away."""
    happens, replaced = {}, {}
    for a in prof.away:
        drawn = {d for d, n in _pick_days(a.freq, eligible_for(a.selector), phase, ("away", a.id), seed,
                                          prof.window_days).items() if n}
        if a.keep is not None:
            chunks = _windows(phase, prof.window_days) or [(phase.dates[0], phase.dates)]
            kept = set()
            for c0, chunk in chunks:
                cand = sorted(d for d in drawn if d in set(chunk))
                r = rng_for(seed, "keep", a.id, c0.isoformat())
                kept |= set(r.sample(cand, min(sample_count(r, a.keep), len(cand))))
            replaced[a.id] = drawn - kept
            drawn = kept
        happens[a.id] = drawn
    return happens, replaced


def _build_days(phase: Phase, seed: int, tz: ZoneInfo, dropped: Counter,
                suppress: dict[date, set[str]] | None = None) -> list[DayCtx]:
    """`suppress`: date -> block ids whose occurrence switches off `unless_after` shifts on that date."""
    prof = phase.profile
    suppress = suppress or {}
    tt_tags, tt_values = _timetable(prof, seed)
    nights = _night_sets(prof, seed, phase.dates) if prof.night_sets else {}

    def eligible_for(sel):
        return lambda d: sel.matches(static_tags(prof, weekday(d), tt_tags), weekday(d), nights.get(d, set()))

    happens, replaced_days = _away_days(prof, phase, seed, eligible_for)
    out = []
    for d in phase.dates:
        wd = weekday(d)
        tags = static_tags(prof, wd, tt_tags)
        ns = nights.get(d, set())
        timetable = tt_values[wd]
        res = _Resolver(d, tz, {}, timetable)

        wake = _anchor(prof.wake, tags, wd, ns, seed, d, "wake", res, night=False,
                       suppress=suppress.get(d, set()))
        res.named["wake"] = wake

        away: list[AwayOcc] = []
        replaced: dict[str, tuple[datetime, datetime]] = {}
        skipped = []
        sleep_base = None
        for a in prof.away:
            is_replaced = d in replaced_days.get(a.id, ())
            if d not in happens[a.id] and not is_replaced:
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
                dropped[f"away {a.id}: empty"] += 1
                continue
            if is_replaced:   # at home instead; blocks with `replaces` run in this period
                replaced[a.id] = (start, end)
                res.named[f"replaced.{a.id}.start"], res.named[f"replaced.{a.id}.end"] = start, end
                if a.sleep_when_replaced:
                    sleep_base = end
                continue
            if a.attend_share is not None and rng_for(seed, d.isoformat(), "attend", a.id).random() >= a.attend_share:
                skipped.append((a.id, start, end, a.skipped_allow))   # stays home, mostly idle
                continue
            away.append(AwayOcc(a.id, start, end, a.replaces))
            res.named[f"away.{a.id}.start"], res.named[f"away.{a.id}.end"] = start, end
            if a.sleep_after_return is not None:
                sleep_base = end + _seconds(r, a.sleep_after_return)

        sleep = _anchor(prof.sleep, tags, wd, ns, seed, d, "sleep", res, night=True, base=sleep_base,
                        suppress=suppress.get(d, set()))
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
        x = prof.duration_noise   # day-to-day volume noise: one factor per day (keyed by date, not by phase)
        factor = rng_for(seed, d.isoformat(), "noise").uniform(1 - x, 1 + x) if x else 1.0
        out.append(DayCtx(d, phase, tags, timetable, wake, sleep, baseline_sleep, away, ns, forbid, factor,
                          replaced, skipped))
    return out


def _anchor(rules, tags, wd, nights, seed, d, name, res, *, night, base=None, shifts=True,
            suppress=frozenset()) -> datetime:
    matching = [r for r in rules if r.selector.matches(tags, wd, nights)]
    if base is None:
        rule = next((r for r in matching if r.value is not None), None)
        if rule is None:
            raise ValueError(f"no {name} anchor matches {d} ({wd}, {sorted(tags)})")
        dist = rule.value
        sd = 1.0
        for r in matching:
            sd *= r.sd_scale or 1.0
        if sd != 1.0 and dist.kind == "normal":   # same draw, wider spread: mean + z * sd * factor
            dist = Dist("normal", (dist.params[0], dist.params[1] * sd), dist.unit)
        secs = dist.sample(rng_for(seed, d.isoformat(), name))
        if night and secs < NOON:
            secs += DAY
        base = local(d, secs, res.tz)
    if shifts:
        for i, rule in enumerate(rules):
            if rule.shift is None or rule not in matching:
                continue
            if rule.unless_after and rule.unless_after in suppress:
                continue
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
    steps: list[tuple[int, Step, timedelta]] | None = None   # (position in the sequence, step, duration)


def _duration(r: random.Random, dist: Dist, block: Block, ctx: DayCtx, inst: float) -> timedelta:
    secs = dist.sample(r) * inst
    if block.noise:
        secs *= ctx.duration_factor
    return timedelta(seconds=round(secs))


def _draw(r: random.Random, block: Block, ctx: DayCtx, inst: float):
    """Duration of one occurrence; for a sequence also its steps (probability first, then duration)."""
    if block.sequence is None:
        return _duration(r, block.duration, block, ctx, inst), None
    steps = []
    for i, st in enumerate(block.sequence, start=1):
        if st.probability < 1 and r.random() >= st.probability:
            continue
        steps.append((i, st, _duration(r, st.duration, block, ctx, inst)))
    return sum((d for _, _, d in steps), timedelta()), steps


def _occurrences(block: Block, ctx: DayCtx, k: int, seed: int, tz: ZoneInfo, plan: Plan) -> list[_Occ]:
    if block.group == "evening" and any(a.replaces == "evening" for a in ctx.away):
        plan.dropped["evening replaced (away)"] += k
        return []
    r = rng_for(seed, ctx.date.isoformat(), "block", block.id)
    named = {"wake": ctx.wake, "sleep": ctx.sleep, "baseline_sleep": ctx.baseline_sleep}
    named.update({f"away.{a.id}.{p}": getattr(a, p) for a in ctx.away for p in ("start", "end")})
    named.update({f"replaced.{i}.start": s for i, (s, _) in ctx.replaced.items()})
    named.update({f"replaced.{i}.end": e for i, (_, e) in ctx.replaced.items()})
    res = _Resolver(ctx.date, tz, named, ctx.timetable)
    inst = instance_factor(seed, "duration_scale", block.id, block.duration_scale)

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
            dur, steps = _draw(r, block, ctx, inst)
            out.append(_Occ(block, ctx, start, dur, start, start + dur + timedelta(seconds=block.max_delay),
                            steps=steps))
    elif block.placement == "fill":
        if k:
            lo = res(block.at, r, night=block.night)
            hi = res(block.to, r, night=block.night, after=lo) if lo else None
            if lo is None or hi is None:
                plan.dropped[f"{block.id}: reference missing that day"] += 1
                return []
            lo, hi = clip(lo, hi)
            if inst != 1.0:   # duration_scale on a fill block: shorter window from its start
                hi = min(hi, lo + (hi - lo) * inst)
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
            dur, steps = _draw(r, block, ctx, inst)
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
            out.append(_Occ(block, ctx, start, dur, lo, hi, steps=steps))
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
        # (start, end, reason, allowed block ids): away periods, forbidden windows, skipped periods
        self.blockers = blockers
        self.placed: list[Entry] = []

    def _blockers(self, s, e, block_id):
        return [b for b in self.blockers if _overlap(s, e, b[0], b[1]) and block_id not in b[3]]

    def blocked(self, s, e, block_id: str) -> str | None:
        if s < self.horizon[0] or e > self.horizon[1]:
            return "outside the plan"
        hits = self._blockers(s, e, block_id)
        return hits[0][2] if hits else None

    def conflicts(self, s, e, role: str, exclusive: bool) -> list[Entry]:
        return [p for p in self.placed if _overlap(s, e, p.start, p.end)
                and (p.role == role or p.exclusive or exclusive)]

    def free_pieces(self, s, e, role, exclusive, block_id) -> list[tuple[datetime, datetime]]:
        cuts = [(p.start, p.end) for p in self.conflicts(s, e, role, exclusive)]
        cuts += [(b[0], b[1]) for b in self._blockers(s, e, block_id)]
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


def _default_mix(activity: str) -> dict[str, float] | None:
    key = catalog.default_mix(activity)
    return {key: 1.0} if key else None


def _entry(o: _Occ, s, e, block_id, *, activity: str | None = None, step: Step | None = None) -> Entry:
    """A plan row of occurrence `o`. `activity`: a part of a split block; `step`: a step of a sequence."""
    b, ctx = o.block, o.ctx
    if step is not None:
        act, mix, pages, dwell, lookups = step.activity, step.mix, step.pages, step.dwell, step.lookups
    elif activity is not None:
        act, mix, pages, dwell, lookups = activity, None, None, None, None
    else:
        act, mix, pages, dwell, lookups = b.activity, b.mix, b.pages, b.dwell, b.lookups
    return Entry(start=s, end=e, role=b.device, activity=act, block_id=block_id, profile_block=b.id,
                 day=ctx.date, phase=ctx.phase.name, profile=ctx.phase.profile.name,
                 mix=mix or _default_mix(act), pages=pages, dwell=dwell, lookups=lookups,
                 platform=b.platform, exclusive=b.exclusive if step is None and activity is None else False,
                 options=b.options, flag=b.flag, window=(o.lo, o.hi))


def _letter(i: int) -> str:
    return chr(ord("a") + i) if i < 26 else f"z{i}"


def _place(o: _Occ, board: _Board, plan: Plan) -> list[Entry]:
    b = o.block
    base_id = f"{o.ctx.date:%Y%m%d}-{b.id}-{o.n:02d}"
    if b.splittable:
        pieces = board.free_pieces(o.start, o.start + o.dur, b.device, b.exclusive, b.id)
        segs: list[tuple[datetime, datetime, str | None]] = [(s, e, None) for s, e in pieces]
        if b.split:   # consecutive parts of the window by share, then cut by the free pieces
            parts, t = [], o.start
            for i, (act, share) in enumerate(b.split):
                end = o.start + o.dur if i == len(b.split) - 1 else t + o.dur * share
                parts.append((t, end, act))
                t = end
            segs = [(max(s, p0), min(e, p1), act) for s, e in pieces for p0, p1, act in parts
                    if (min(e, p1) - max(s, p0)).total_seconds() >= MIN_PIECE]
        if not segs:
            plan.dropped["no free time in window"] += 1
            return []
        return [_entry(o, s, e, base_id if len(segs) == 1 else f"{base_id}{_letter(i)}", activity=act)
                for i, (s, e, act) in enumerate(segs)]
    t = o.start
    while True:
        e = t + o.dur
        if e > o.hi:
            plan.dropped["no longer fits (overlap)"] += 1
            return []
        why = board.blocked(t, e, b.id)
        if why:
            plan.dropped[why] += 1
            return []
        c = board.conflicts(t, e, b.device, b.exclusive)
        if not c:
            break
        t = max(p.end for p in c)
    if o.steps is None:
        return [_entry(o, t, e, base_id)]
    out = []
    for i, st, dur in o.steps:   # back to back; -s<n> = position in the profile's sequence
        out.append(_entry(o, t, t + dur, f"{base_id}-s{i}", step=st))
        t += dur
    return out


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


def _select(block: Block, phase: Phase, by_date: dict[date, DayCtx], seed: int, tz: ZoneInfo,
            tt_tags, nights) -> dict[date, int]:
    """Days (and occurrences per day) of one block in one phase."""
    prof = phase.profile
    if block.replaces is not None:
        return {d: 1 for d in phase.dates if block.replaces in by_date[d].replaced}
    limit = block.only_sleep_before

    def eligible(d: date) -> bool:
        if not block.selector.matches(static_tags(prof, weekday(d), tt_tags), weekday(d), nights.get(d, set())):
            return False
        c = by_date.get(d)
        if limit is not None and c is not None:   # days outside the phase: only the selector counts
            return c.sleep <= local(d, limit + DAY if limit < NOON else limit, tz)
        return True
    scale = instance_factor(seed, "scale", block.id, block.freq.scale)
    return _pick_days(block.freq, eligible, phase, ("block", block.id), seed, prof.window_days, scale)


def build_plan(profile: Profile, seed: int, start: date, days: int, *, baseline: Profile | None = None,
               baseline_days: int = 0, any_start: bool = False) -> Plan:
    """`start` is the first warm-up day. The first window day must be the profile's `start_weekday`
    (catalog §1; decided 23.10: warm-up on the Sunday before), unless `any_start` (tests, pilots)."""
    if baseline_days and baseline is None:
        raise ValueError("baseline_days needs a baseline profile")
    tz = ZoneInfo(profile.timezone)
    phases = make_phases(profile, baseline, start, days, baseline_days)
    horizon = (local(start, 0, tz), local(start + timedelta(days=days), 0, tz))
    plan = Plan(seed, profile, phases, [], [], horizon)

    first_window = start + timedelta(days=profile.warmup_days)
    if weekday(first_window) != profile.start_weekday:
        want = WEEKDAYS[(WEEKDAYS.index(profile.start_weekday) - profile.warmup_days) % 7]
        earlier = start - timedelta(days=(start.weekday() - WEEKDAYS.index(want)) % 7)
        msg = (f"the 14-day window would start on {first_window} ({weekday(first_window)}), catalog §1 wants a "
               f"{profile.start_weekday}: with {profile.warmup_days} warm-up day(s) --start must be a {want}, "
               f"e.g. {earlier}")
        if not any_start:
            raise ValueError(msg + " (--any-start allows other days, e.g. for pilots)")
        plan.warnings.append(msg)

    occs: list[_Occ] = []
    for phase in phases:
        prof = phase.profile
        tt_tags, _ = _timetable(prof, seed)
        nights = _night_sets(prof, seed, phase.dates) if prof.night_sets else {}
        blocks = {b.id: b for b in prof.blocks}
        selection: dict[str, dict[date, int]] = {}

        needed = {r.unless_after for r in prof.wake + prof.sleep if r.unless_after}
        if needed:   # pass 1: which nights have the block; pass 2: rebuild the days without those shifts
            ctxs = _build_days(phase, seed, tz, Counter())
            by_date = {c.date: c for c in ctxs}
            suppress: dict[date, set[str]] = defaultdict(set)
            for bid in sorted(needed):
                selection[bid] = _select(blocks[bid], phase, by_date, seed, tz, tt_tags, nights)
                for d, n in selection[bid].items():
                    if n:
                        suppress[d + timedelta(days=1) if blocks[bid].night else d].add(bid)
            ctxs = _build_days(phase, seed, tz, plan.dropped, suppress)
        else:
            ctxs = _build_days(phase, seed, tz, plan.dropped)
        plan.days.extend(ctxs)
        by_date = {c.date: c for c in ctxs}

        for block in prof.blocks:
            if block.id not in selection:
                selection[block.id] = _select(block, phase, by_date, seed, tz, tt_tags, nights)
        for block in prof.blocks:
            for cid in block.cancels:
                for d, n in selection[block.id].items():
                    if n and selection[cid].get(d):
                        plan.dropped[f"cancelled by {block.id}"] += selection[cid][d]
                        selection[cid][d] = 0
        for block in prof.blocks:
            for d in phase.dates:
                if selection[block.id].get(d):
                    occs.extend(_occurrences(block, by_date[d], selection[block.id][d], seed, tz, plan))

    blockers = [(a.start, a.end, "away", frozenset()) for c in plan.days for a in c.away]
    blockers += [(s, e, "forbidden window", frozenset()) for c in plan.days for s, e in c.forbid]
    blockers += [(s, e, f"{i} skipped (at home, idle)", allow) for c in plan.days for i, s, e, allow in c.skipped]
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
