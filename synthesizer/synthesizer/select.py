"""Plan rows -> snippet choices -> segments (README §3–§4). No packets are touched here.

A segment places the packets of one snippet between two offsets (relative to the snippet's recorded start) at an
absolute instant on a target device. Everything is in integer µs since the epoch, so DST needs no special case.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from pathlib import Path

from . import catalog
from .catalog import S
from .library import iso_to_us, read_index, snippet_path

OPTION_KEYS = ("mic_share", "lookups")
FLAG_ORDER = ("role", "mix", "options")   # fallback flags, most important first


# -------------------- inputs --------------------

@dataclass
class Snippet:
    sid: str
    activity: str
    companions: tuple[str, ...]
    role: str
    client_ip: str
    client_mac: str
    start_us: int
    dur_us: int
    tail_us: int
    first_page_us: int | None
    cats: list[set[str]]
    mic_share: str
    lookups: str
    flags: set[str]
    path: Path

    @property
    def head_us(self) -> int:
        """Start of the part that chains/loops repeat. Page activities: the first page request, so a further body
        is a new page without a second browser start; the rest: catalog.head_us."""
        if self.activity in catalog.CHAIN:
            h = max((self.first_page_us or 0) - 50_000, 0)   # 50 ms before the page's DNS query
        else:
            h = catalog.head_us(self.activity, self.dur_us)
        return min(h, self.dur_us)

    @property
    def body_us(self) -> int:
        return self.dur_us - self.head_us


def load_snippets(library: str | Path) -> list[Snippet]:
    out = []
    for r in read_index(library):
        start = iso_to_us(r["start"])
        out.append(Snippet(
            sid=r["snippet_id"], activity=r["activity_id"],
            companions=tuple(c for c in r["companions"].split(";") if c),
            role=r["role"], client_ip=r["client_ip"], client_mac=r["client_mac"], start_us=start,
            dur_us=round(float(r["duration_s"]) * S), tail_us=round(float(r["tail_s"] or 0) * S),
            first_page_us=round(float(r["first_page_s"]) * S) if r.get("first_page_s") else None,
            cats=[set(c.split("|")) for c in r["categories"].split(";") if c],
            mic_share=r["mic_share"], lookups=r["lookups"],
            flags={f for f in r["flags"].split(";") if f}, path=snippet_path(library, r["snippet_id"])))
    return out


@dataclass
class PlanRow:
    raw: dict
    block_id: str
    device: str
    activity: str
    start_us: int
    end_us: int
    mix: dict[str, float]
    options: dict[str, str]
    seed: str
    companion_of: str
    day: str

    @property
    def duration_us(self) -> int:
        return self.end_us - self.start_us


def load_plan(path: str | Path, days: list[str] | None = None) -> list[PlanRow]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        if days and r.get("day") not in days:
            continue
        opts = catalog.parse_options(r.get("options"))
        if r.get("lookups"):
            opts["lookups"] = r["lookups"]
        out.append(PlanRow(raw=r, block_id=r["block_id"], device=r["device"], activity=r["activity_id"],
                           start_us=iso_to_us(r["start"]), end_us=iso_to_us(r["end"]),
                           mix=catalog.parse_mix(r.get("mix")), options=opts, seed=r.get("seed", ""),
                           companion_of=r.get("companion_of", ""), day=r.get("day", "")))
    return out


# -------------------- matching --------------------

def _norm_mic(v: str) -> str:
    return "" if not v or float(v) == 1.0 else f"{float(v):g}"


def match(s: Snippet, row: PlanRow, role: str, companions: tuple[str, ...]) -> tuple[tuple[int, ...], float] | None:
    """(rank, weight) of a snippet for a plan unit, None if it cannot be used at all.
    rank = one entry per FLAG_ORDER (0 = matches); lower is better, compared lexicographically."""
    if s.activity != row.activity or s.companions != companions or "empty" in s.flags:
        return None
    role_bad = int(s.role != role)
    weight = 1.0
    mix_level = 0
    if row.mix:
        known = [c for c in s.cats if c]
        if not known:
            mix_level = 1
        elif all(c & row.mix.keys() for c in known):
            weight = sum(max(row.mix.get(x, 0) for x in c) for c in known) / len(known)
        elif any(c & row.mix.keys() for c in known):
            mix_level = 1
        else:
            mix_level = 2
    opt_bad = 0
    if row.activity in ("video_call", "voice_call"):
        opt_bad = int(_norm_mic(row.options.get("mic_share", "")) != _norm_mic(s.mic_share))
    if row.activity == "sh_adjacent_lookup" and row.options.get("lookups"):
        opt_bad = int(row.options["lookups"] != s.lookups)
    return (role_bad, mix_level, opt_bad), weight


def rank_flags(rank: tuple[int, ...]) -> str:
    names = []
    for name, v in zip(FLAG_ORDER, rank):
        if v:
            names.append(f"{name}_fallback")
    return ";".join(names) or "exact"


def is_bounded(row: PlanRow) -> bool:
    return row.activity in catalog.BOUNDED or (row.activity == "phone_check" and bool(row.raw.get("pages")))


def duration_factor(s: Snippet, row: PlanRow) -> float:
    d = max(row.duration_us, 1)
    if is_bounded(row):
        return 1.0 if s.dur_us <= d else d / s.dur_us
    if row.activity in catalog.CHAIN:
        return 0.25 + min(1.0, s.dur_us / d)   # several pages from several snippets are fine
    return 0.02 + min(1.0, s.dur_us / d)       # a loop repeats one snippet: strongly prefer long ones


def candidates(snippets: list[Snippet], row: PlanRow, role: str, companions: tuple[str, ...],
               strict: bool) -> tuple[list[tuple[Snippet, float]], str]:
    scored = [(s, m) for s in snippets if (m := match(s, row, role, companions))]
    if not scored:
        return [], "no_snippet"
    best = min(m[0] for _, m in scored)
    if strict and any(best):
        return [], "no_exact_snippet"
    return [(s, m[1] * duration_factor(s, row)) for s, m in scored if m[0] == best], rank_flags(best)


def _choose(rng: random.Random, cands: list[tuple[Snippet, float]]) -> Snippet:
    cands = sorted(cands, key=lambda c: c[0].sid)   # independent of index order
    total = sum(w for _, w in cands)
    if total <= 0:
        return rng.choice(cands)[0]
    return rng.choices([s for s, _ in cands], weights=[w for _, w in cands])[0]


# -------------------- segments --------------------

@dataclass
class Segment:
    snippet: Snippet
    src_from_us: int
    src_to_us: int
    at_us: int                    # absolute output time of src_from_us
    copy: int                     # 0 = first use in this block; >0 = further body (new ports if the activity wants them)
    new_ports: bool
    block_ids: tuple[str, ...]
    device: str
    part: str = "main"            # main / body / tail
    packets: int = 0
    bytes: int = 0

    @property
    def end_us(self) -> int:
        return self.at_us + self.src_to_us - self.src_from_us


@dataclass
class UnitPlan:
    rows: list[PlanRow]           # host first, then companions built into the same segments
    method: str
    match: str
    segments: list[Segment] = field(default_factory=list)
    note: str = ""


def plan_unit(rows: list[PlanRow], role: str, snippets: list[Snippet], rng: random.Random, strict: bool,
              limit_us: int | None) -> UnitPlan:
    """Segments for one host row (+ companions served by one group snippet)."""
    row = rows[0]
    companions = tuple(sorted(r.activity for r in rows[1:]))
    block_ids = tuple(r.block_id for r in rows)
    cands, quality = candidates(snippets, row, role, companions, strict)
    if not cands:
        return UnitPlan(rows, "none", quality)
    D = row.duration_us
    first = _choose(rng, cands)
    segs = [Segment(first, 0, min(first.dur_us, D), row.start_us, 0, False, block_ids, row.device)]
    t = segs[0].src_to_us
    last = first
    copy = 0
    if is_bounded(row):
        method = "bounded"
    else:
        method = "loop" if (row.activity in catalog.LOOP or companions) else "chain"
        new_ports = row.activity in catalog.NEW_PORTS and not companions
        pool = [(s, w) for s, w in cands if s.body_us >= catalog.MIN_BODY_S * S]
        while t < D:
            if method == "loop":
                nxt = first if first.body_us >= catalog.MIN_BODY_S * S else None
            else:
                nxt = _choose(rng, pool) if pool else None
            if nxt is None:
                quality = ";".join(filter(lambda x: x != "exact", [quality, "short"])) or "short"
                break
            copy += 1
            take = min(nxt.body_us, D - t)
            segs.append(Segment(nxt, nxt.head_us, nxt.head_us + take, row.start_us + t, copy, new_ports,
                                block_ids, row.device, "body"))
            t += take
            last = nxt
    last_seg = segs[-1]
    if last.tail_us > 0:
        segs.append(Segment(last, last.dur_us, last.dur_us + last.tail_us, row.start_us + t, last_seg.copy,
                            last_seg.new_ports, block_ids, row.device, "tail"))
    if limit_us is not None:
        segs = _clip(segs, limit_us)
    if method != "bounded" and copy == 0:
        method = "trim"
    return UnitPlan(rows, method, quality, segs)


def _clip(segs: list[Segment], limit_us: int) -> list[Segment]:
    out = []
    for s in segs:
        if s.at_us >= limit_us:
            continue
        if s.end_us > limit_us:
            s.src_to_us = s.src_from_us + (limit_us - s.at_us)
        out.append(s)
    return out


def plan_all(plan: list[PlanRow], snippets: list[Snippet], roles: dict[str, str], synth_seed: str | None,
             strict: bool = False) -> list[UnitPlan]:
    """All plan rows -> UnitPlans. Each unit has its own RNG f"{seed}/{block_id}" (scheduler/runner scheme)."""
    by_id = {r.block_id: r for r in plan}
    comps: dict[str, list[PlanRow]] = {}
    for r in plan:
        if r.companion_of and r.companion_of in by_id:
            comps.setdefault(r.companion_of, []).append(r)
    hosts = [r for r in plan if not (r.companion_of and r.companion_of in by_id)]

    # A unit's packets may not run into the next block on the same device (tails, rounding).
    next_start: dict[str, int] = {}
    by_dev: dict[str, list[PlanRow]] = {}
    for r in hosts:
        if r.activity != "away":
            by_dev.setdefault(r.device, []).append(r)
    for dev, rows in by_dev.items():
        rows.sort(key=lambda r: r.start_us)
        for a, b in zip(rows, rows[1:]):
            next_start[a.block_id] = b.start_us

    units: list[UnitPlan] = []
    for r in sorted(hosts, key=lambda r: (r.start_us, r.device)):
        seed = synth_seed if synth_seed is not None else r.seed
        rng = random.Random(f"{seed}/{r.block_id}")
        limit = next_start.get(r.block_id)
        if r.activity == "away":
            units.append(UnitPlan([r], "away", "-"))
            continue
        if r.activity in catalog.NOTHING:
            units.append(UnitPlan([r], "idle", "-"))
            continue
        role = roles[r.device]
        group = comps.get(r.block_id, [])
        if group:
            up = plan_unit([r] + group, role, snippets, rng, strict, limit)
            if up.method != "none":
                units.append(up)
                continue
            # no recorded group: host and companions from solo snippets, overlaid on the same device
            for member in [r] + group:
                m_rng = random.Random(f"{seed}/{member.block_id}")
                up = plan_unit([member], role, snippets, m_rng, strict, limit)
                up.note = "overlay"
                units.append(up)
            continue
        units.append(plan_unit([r], role, snippets, rng, strict, limit))
    return units
