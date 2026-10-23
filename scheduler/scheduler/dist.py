"""Distribution notation of activity-catalog §1, parsed into samplers.

Values (all in seconds; a time of day is seconds since local midnight):
    "06:30"                    time of day (also '"06:30"', as written in some profiles)
    15m, 2h, 90s, 300          duration
    5-15m, 1h-3h, 10-18        uniform range (unit at the end applies to both ends; integers for counts)
    'N("06:30", 15m)'          normal, clipped to mean ± 3 SD
    'U(2h, 5h)'                uniform
    'Poisson(2.5)'             Poisson (counts)
    {p: [.8, .2], values: [...]}  mixture
Counts additionally accept `clip: [lo, hi]` next to them (see spec.py) and are rounded.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass

TIME, DURATION, NUMBER = "time", "duration", "number"
SD_CLIP = 3.0

_TIME_RE = re.compile(r'^"?(\d{1,2}):(\d{2})"?$')
_DUR_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(s|m|h)?$")
_RANGE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(s|m|h)?\s*-\s*(\d+(?:\.\d+)?)\s*(s|m|h)?$")
_FUNC_RE = re.compile(r"^(N|U|Poisson)\((.*)\)$")
_UNIT = {"s": 1, "m": 60, "h": 3600}


class DistError(ValueError):
    pass


@dataclass(frozen=True)
class Dist:
    kind: str                 # const | uniform | uniform_int | normal | poisson | mixture
    params: tuple
    unit: str                 # TIME, DURATION or NUMBER

    def sample(self, rng: random.Random) -> float:
        k, p = self.kind, self.params
        if k == "const":
            return p[0]
        if k == "uniform":
            return rng.uniform(p[0], p[1])
        if k == "uniform_int":
            return float(rng.randint(int(p[0]), int(p[1])))
        if k == "normal":
            mean, sd = p
            return min(max(rng.gauss(mean, sd), mean - SD_CLIP * sd), mean + SD_CLIP * sd)
        if k == "poisson":
            return float(_poisson(rng, p[0]))
        if k == "mixture":
            weights, parts = p
            return rng.choices(parts, weights=weights)[0].sample(rng)
        raise AssertionError(k)

    def bounds(self) -> tuple[float, float]:
        """Smallest and largest value the sampler can return (Poisson: mean + 10 SD)."""
        k, p = self.kind, self.params
        if k == "const":
            return p[0], p[0]
        if k in ("uniform", "uniform_int"):
            return p[0], p[1]
        if k == "normal":
            return p[0] - SD_CLIP * p[1], p[0] + SD_CLIP * p[1]
        if k == "poisson":
            return 0.0, p[0] + 10 * math.sqrt(p[0]) + 1
        if k == "mixture":
            b = [d.bounds() for d in p[1]]
            return min(x[0] for x in b), max(x[1] for x in b)
        raise AssertionError(k)


def _poisson(rng: random.Random, lam: float) -> int:
    # Knuth; fine for the small λ used in profiles
    limit, k, prod = math.exp(-lam), 0, rng.random()
    while prod > limit:
        k += 1
        prod *= rng.random()
    return k


def _atom(text: str, unit: str) -> float:
    """One argument inside N()/U(): a time of day, a duration or a plain number."""
    t = text.strip()
    m = _TIME_RE.match(t)
    if m and (unit == TIME or t.startswith('"')):
        h, mi = int(m.group(1)), int(m.group(2))
        if mi > 59 or h > 47:
            raise DistError(f"bad time '{text}'")
        return float(h * 3600 + mi * 60)
    m = _DUR_RE.match(t)
    if m:
        value = float(m.group(1))
        return value * _UNIT[m.group(2)] if m.group(2) else value   # bare number: seconds for durations
    raise DistError(f"cannot read '{text}'")


def parse(value, unit: str) -> Dist:
    """Parse a profile value into a Dist. `unit` says what a bare value means (TIME/DURATION/NUMBER)."""
    if isinstance(value, Dist):
        return value
    if isinstance(value, dict):
        if set(value) != {"p", "values"} or len(value["p"]) != len(value["values"]) or not value["p"]:
            raise DistError(f"mixture needs equally long `p` and `values`: {value}")
        return Dist("mixture", (tuple(float(x) for x in value["p"]),
                                tuple(parse(v, unit) for v in value["values"])), unit)
    if isinstance(value, bool):
        raise DistError(f"unexpected boolean {value}")
    if isinstance(value, (int, float)):
        return Dist("const", (float(value),), unit)
    if not isinstance(value, str):
        raise DistError(f"unexpected value {value!r}")
    text = value.strip()

    m = _FUNC_RE.match(text)
    if m:
        name, args = m.group(1), [a for a in m.group(2).split(",")]
        if name == "Poisson":
            if len(args) != 1:
                raise DistError(f"Poisson takes one argument: {text}")
            return Dist("poisson", (float(args[0]),), unit)
        if len(args) != 2:
            raise DistError(f"{name} takes two arguments: {text}")
        a = _atom(args[0], unit)
        if name == "N":
            sd = _atom(args[1], DURATION if unit == TIME else unit)
            if sd < 0:
                raise DistError(f"negative SD in {text}")
            return Dist("normal", (a, sd), unit)
        b = _atom(args[1], unit)
        if a > b:
            raise DistError(f"U(a, b) needs a <= b: {text}")
        return Dist("uniform", (a, b), unit)

    if unit == TIME:
        m = _TIME_RE.match(text)
        if not m:
            raise DistError(f"bad time '{value}' (use \"HH:MM\" or N()/U())")
        return Dist("const", (_atom(text, TIME),), unit)

    m = _RANGE_RE.match(text)
    if m:
        lo_u = m.group(2) or m.group(4)
        hi_u = m.group(4) or m.group(2)
        lo = float(m.group(1)) * (_UNIT[lo_u] if lo_u else 1)
        hi = float(m.group(3)) * (_UNIT[hi_u] if hi_u else 1)
        if lo > hi:
            raise DistError(f"range '{value}' has lo > hi")
        if unit == NUMBER:
            if lo != int(lo) or hi != int(hi):
                raise DistError(f"count range '{value}' must be integers")
            return Dist("uniform_int", (lo, hi), unit)
        return Dist("uniform", (lo, hi), unit)
    m = _DUR_RE.match(text)
    if m:
        return Dist("const", (_atom(text, unit),), unit)
    raise DistError(f"cannot read '{value}'")


def parse_duration(value) -> Dist:
    d = parse(value, DURATION)
    if d.bounds()[0] < 0:
        raise DistError(f"negative duration '{value}'")
    return d


def sample_count(rng: random.Random, dist: Dist, clip: tuple[int, int] | None = None) -> int:
    """Sample a count: round to the nearest integer, then clip."""
    n = int(round(dist.sample(rng)))
    if clip:
        n = min(max(n, clip[0]), clip[1])
    return max(n, 0)
