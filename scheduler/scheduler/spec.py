"""Load a profile YAML (scheduler/profiles/<name>.yaml), resolve `extends` + `patch`, validate it.

The format is described in scheduler/README.md §2. Everything that can be checked without
sampling is checked here, so a typo fails at load time and not in the middle of a plan.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import catalog
from .dist import DURATION, NUMBER, TIME, Dist, DistError, parse, parse_duration

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DEFAULT_MAX_DELAY = 30 * 60

PERIOD_KEYS = ("per_week", "days_per_week", "per_window", "nights_per_window")
_SELECTOR_KEYS = {"day_types", "days", "nights"}
_FREQ_KEYS = {"count", "clip", "scale", *PERIOD_KEYS}
BLOCK_KEYS = _SELECTOR_KEYS | _FREQ_KEYS | {
    "id", "group", "at", "from", "to", "within", "duration", "device", "activity", "mix", "pages", "dwell",
    "with", "voice", "platform", "max_delay", "min_gap", "not_before", "night", "noise", "lookups",
    "duration_scale", "only_if", "replaces", "cancels", "split", "sequence", "flag", "options"}
STEP_KEYS = {"activity", "duration", "probability", "mix", "pages", "dwell", "lookups"}
AWAY_KEYS = _SELECTOR_KEYS | _FREQ_KEYS | {
    "id", "from", "to", "length", "not_before", "replaces", "sleep_after_return",
    "attend_share", "skipped_allow", "keep_per_window", "sleep_when_replaced"}
ANCHOR_KEYS = _SELECTOR_KEYS | {"value", "shift", "sd_scale", "unless_after"}
TOP_KEYS = {"profile", "source", "tier", "extends", "timezone", "window_days", "warmup_days", "start_weekday",
            "devices", "day_types", "timetable", "anchors", "away", "blocks", "night_sets", "patch", "noise"}
PATCH_KEYS = {"anchors", "modify", "add", "remove", "scale", "forbid"}

_REF_RE = re.compile(r"^(wake|sleep|baseline_sleep|timetable\.[a-z_][a-z0-9_]*"
                     r"|(?:away|replaced)\.[a-z_][a-z0-9_]*\.(?:start|end))"
                     r"(?:\s*([+-])\s*(\S.*))?$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class SpecError(ValueError):
    pass


# --- parsed objects ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimeRef:
    """A time of day: a named reference (wake, sleep, timetable.x, away.id.end, ...) or a distribution,
    optionally ± a duration."""
    text: str
    name: str | None
    dist: Dist | None
    sign: int = 0
    offset: Dist | None = None


@dataclass(frozen=True)
class Selector:
    day_types: frozenset[str] | None = None   # None = all
    days: frozenset[str] | None = None
    nights: str | None = None                 # night set name: the night of day d is in the set

    def matches(self, tags: set[str], weekday: str, nights: set[str]) -> bool:
        if self.day_types is not None and not (self.day_types & tags):
            return False
        if self.days is not None and weekday not in self.days:
            return False
        if self.nights is not None and self.nights not in nights:
            return False
        return True


@dataclass(frozen=True)
class Freq:
    key: str                     # "count" (every eligible day) or one of PERIOD_KEYS
    period_n: Dist | None        # how many days/occurrences per week/window
    count: Dist                  # occurrences on a selected day
    clip: tuple[int, int] | None  # clips `count` if given explicitly, else period_n
    clip_count: bool
    scale: Dist | None = None    # "baseline × f": f drawn once per seed; multiplies count (or the period's n)


@dataclass(frozen=True)
class Block:
    id: str
    index: int                   # list position = priority for overlaps
    selector: Selector
    freq: Freq
    placement: str               # at | from_duration | fill | within
    at: TimeRef | None
    to: TimeRef | None
    within: tuple[TimeRef, TimeRef] | None
    duration: Dist | None
    device: str
    activity: str
    mix: dict[str, float] | None
    pages: str | None
    dwell: str | None
    lookups: str | None
    with_: str | None
    voice: bool
    platform: str | None
    max_delay: float
    min_gap: float
    not_before: TimeRef | None
    night: bool
    group: str | None
    noise: bool                  # False: the day's duration noise does not apply (e.g. thresholds like <= 5 min)
    duration_scale: Dist | None = None   # "× f" on durations (fill blocks: on the window length), f once per seed
    only_sleep_before: float | None = None   # only on days whose sleep onset is <= this time (night axis)
    replaces: str | None = None  # runs on the days an away period was drawn but not kept (keep_per_window)
    cancels: tuple[str, ...] = ()  # blocks that don't run on the days this block runs
    split: tuple[tuple[str, float], ...] | None = None   # consecutive parts of a fill window by share
    sequence: tuple["Step", ...] | None = None           # steps run back to back as one unit
    flag: str | None = None      # e.g. "sensitive": copied to the plan's `flag` column
    options: str | None = None   # recorded in the plan only (no runner option yet), e.g. "mic_share=0.1"

    @property
    def exclusive(self) -> bool:
        """Calls (and a gaming session with voice chat) block foreground activity on all devices."""
        return self.activity in catalog.CALLS or (self.activity == "gaming_session" and self.voice)

    @property
    def splittable(self) -> bool:
        return self.placement == "fill" or self.activity in catalog.SPLITTABLE


@dataclass(frozen=True)
class Step:
    activity: str
    duration: Dist
    probability: float
    mix: dict[str, float] | None
    pages: str | None
    dwell: str | None
    lookups: str | None


@dataclass(frozen=True)
class Away:
    id: str
    selector: Selector
    freq: Freq
    start: TimeRef
    end: TimeRef | None
    length: Dist | str | None   # a duration or "timetable.<name>"
    not_before: TimeRef | None
    replaces: str | None
    sleep_after_return: Dist | None
    attend_share: float | None = None     # probability that a drawn period really happens (else: skipped)
    skipped_allow: frozenset[str] = frozenset()   # blocks allowed during a skipped period (all others: no)
    keep: Dist | None = None              # keep_per_window: how many of the drawn periods are kept per window
    sleep_when_replaced: bool = False     # on a replaced day, sleep onset = end of the replaced period


@dataclass(frozen=True)
class AnchorRule:
    selector: Selector
    value: Dist | None
    shift: Dist | None
    sd_scale: float | None = None         # multiplies the SD of the matching normal value (variance × sd_scale²)
    unless_after: str | None = None       # the shift is skipped on the morning after this block's night


@dataclass(frozen=True)
class Forbid:
    start: TimeRef
    end: TimeRef
    night: bool


@dataclass
class Profile:
    name: str
    source: str
    tier: int
    extends: str | None
    root: str                    # tier-0 profile at the bottom of the extends chain (the baseline)
    timezone: str
    window_days: int
    warmup_days: int
    start_weekday: str
    devices: list[str]
    day_types: dict[str, list[str]]
    timetable_tags: dict[str, tuple[int, str, str | None]]   # tag -> (choose, of day type, else tag)
    timetable_values: dict[str, object]                     # name -> Dist or {selector key: Dist}
    wake: list[AnchorRule]
    sleep: list[AnchorRule]
    away: list[Away]
    blocks: list[Block]
    night_sets: dict[str, Freq] = field(default_factory=dict)
    duration_noise: float = 0.0  # ± share; one factor U(1 - x, 1 + x) per day on all block durations
    forbid: list[Forbid] = field(default_factory=list)


# --- loading ------------------------------------------------------------------------------------

def profile_path(name: str) -> Path:
    p = Path(name)
    if p.suffix in (".yaml", ".yml"):
        return p
    return PROFILE_DIR / f"{name}.yaml"


def load_raw(name: str, _seen: tuple[str, ...] = ()) -> dict:
    """The profile as a plain dict, with `extends` and `patch` applied."""
    path = profile_path(name)
    if not path.exists():
        known = ", ".join(sorted(p.stem for p in PROFILE_DIR.glob("*.yaml")))
        raise SpecError(f"profile '{name}' not found ({path}); known: {known}")
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise SpecError(f"{path}: not a YAML mapping")
    unknown = set(raw) - TOP_KEYS
    if unknown:
        raise SpecError(f"{path}: unknown top-level keys {sorted(unknown)}")
    parent = raw.get("extends")
    if not parent:
        if "patch" in raw:
            raise SpecError(f"{path}: `patch` needs `extends`")
        raw["_root"] = raw.get("profile")
        return raw
    if parent in _seen:
        raise SpecError(f"{path}: extends cycle {' -> '.join(_seen + (parent,))}")
    base = load_raw(parent, _seen + (raw.get("profile", name),))
    merged = copy.deepcopy(base)
    for key, value in raw.items():
        if key not in ("patch", "night_sets"):
            merged[key] = copy.deepcopy(value)
    merged["night_sets"] = {**base.get("night_sets", {}), **raw.get("night_sets", {})}
    _apply_patch(merged, raw.get("patch") or {}, path)
    merged["_root"] = base["_root"]
    return merged


def _apply_patch(doc: dict, patch: dict, path: Path) -> None:
    unknown = set(patch) - PATCH_KEYS
    if unknown:
        raise SpecError(f"{path}: unknown patch keys {sorted(unknown)}")
    for anchor, rules in (patch.get("anchors") or {}).items():
        if anchor not in ("wake", "sleep"):
            raise SpecError(f"{path}: patch.anchors.{anchor}: only wake and sleep")
        base = doc.setdefault("anchors", {}).setdefault(anchor, [])
        overrides = [r for r in rules if "value" in r]
        shifts = [r for r in rules if "value" not in r]
        doc["anchors"][anchor] = overrides + base + shifts   # value rules: first match wins
    items = {it["id"]: it for it in doc.get("blocks", []) + doc.get("away", [])}
    for item_id, changes in (patch.get("modify") or {}).items():
        if item_id not in items:
            raise SpecError(f"{path}: patch.modify: no block or away period '{item_id}'")
        for k, v in changes.items():
            if v is None:
                items[item_id].pop(k, None)
            else:
                if k in PERIOD_KEYS or k == "count":   # a new frequency replaces the old one (keep_per_window: filter)
                    for old in ("count", *PERIOD_KEYS):
                        items[item_id].pop(old, None)
                items[item_id][k] = v
    for item_id, factor in (patch.get("scale") or {}).items():
        if item_id not in items:
            raise SpecError(f"{path}: patch.scale: no block '{item_id}'")
        items[item_id]["scale"] = factor
    remove = set(patch.get("remove") or [])
    missing = remove - set(items)
    if missing:
        raise SpecError(f"{path}: patch.remove: unknown ids {sorted(missing)}")
    doc["blocks"] = [b for b in doc.get("blocks", []) if b["id"] not in remove] + list(patch.get("add") or [])
    doc["away"] = [a for a in doc.get("away", []) if a["id"] not in remove]
    doc["forbid"] = list(doc.get("forbid", [])) + list(patch.get("forbid") or [])


def load(name: str) -> Profile:
    raw = load_raw(name)
    where = f"profile '{raw.get('profile', name)}'"
    try:
        return _build(raw)
    except (DistError, SpecError, KeyError, TypeError) as e:
        raise SpecError(f"{where}: {e}") from None


# --- building --------------------------------------------------------------------------------

def _time_ref(value, what: str) -> TimeRef:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        raise SpecError(f"{what}: {value!r} is a number; quote times, e.g. \"14:00\" (unquoted YAML reads 14:00 as 840)")
    if not isinstance(value, str):
        raise SpecError(f"{what}: expected a time, got {value!r}")
    m = _REF_RE.match(value.strip())
    if m:
        offset = parse_duration(m.group(3)) if m.group(3) else None
        sign = (1 if m.group(2) == "+" else -1) if m.group(2) else 0
        return TimeRef(value, m.group(1), None, sign, offset)
    try:
        return TimeRef(value, None, parse(value, TIME))
    except DistError as e:
        raise SpecError(f"{what}: {e}") from None


def _selector(d: dict, day_types: dict, nights: dict, what: str) -> Selector:
    dt = d.get("day_types")
    if dt is None and "days" not in d and "nights" not in d:
        raise SpecError(f"{what}: needs day_types, days or nights")
    sel_types = None
    if dt is not None and dt != "all":
        if isinstance(dt, str):
            dt = [dt]
        for t in dt:
            if t not in day_types:
                raise SpecError(f"{what}: unknown day type '{t}' (known: {', '.join(day_types)})")
        sel_types = frozenset(dt)
    sel_days = None
    if "days" in d:
        bad = [x for x in d["days"] if x not in WEEKDAYS]
        if bad:
            raise SpecError(f"{what}: bad weekdays {bad}")
        sel_days = frozenset(d["days"])
    ns = d.get("nights")
    if ns is not None and ns not in nights:
        raise SpecError(f"{what}: unknown night set '{ns}'")
    return Selector(sel_types, sel_days, ns)


def _freq(d: dict, what: str) -> Freq:
    keys = [k for k in PERIOD_KEYS if k in d]
    if len(keys) > 1:
        raise SpecError(f"{what}: only one of {', '.join(PERIOD_KEYS)} allowed, got {keys}")
    clip = tuple(int(x) for x in d["clip"]) if "clip" in d else None
    if clip and (len(clip) != 2 or clip[0] > clip[1]):
        raise SpecError(f"{what}: clip must be [lo, hi]")
    count = parse(d.get("count", 1), NUMBER)
    if keys:
        key = keys[0]
        if key in ("per_week", "per_window", "keep_per_window") and "count" in d:
            raise SpecError(f"{what}: {key} counts occurrences (one per day); use days_per_week/"
                            "nights_per_window together with count")
        return Freq(key, parse(d[key], NUMBER), count, clip, "count" in d, _scale(d))
    return Freq("count", None, count, clip, True, _scale(d))


def _scale(d: dict) -> Dist | None:
    if "scale" not in d:
        return None
    s = parse(d["scale"], NUMBER)
    if s.bounds()[0] < 0:
        raise SpecError(f"scale must be >= 0: {d['scale']}")
    return s


def _check_keys(d: dict, allowed: set, what: str) -> None:
    unknown = set(d) - allowed
    if unknown:
        raise SpecError(f"{what}: unknown keys {sorted(unknown)}")
    if "id" in allowed and not _ID_RE.match(str(d.get("id", ""))):
        raise SpecError(f"{what}: id must match [a-z][a-z0-9_]*")


def _mix(mix, activity: str, what: str) -> dict[str, float] | None:
    if mix is None:
        if activity in catalog.NEEDS_MIX:
            raise SpecError(f"{what}: {activity} needs a `mix`")
        return None
    if not isinstance(mix, dict) or not mix:
        raise SpecError(f"{what}: mix must be a mapping category -> weight")
    bad = [k for k in mix if k not in catalog.MIX_KEYS]
    if bad:
        raise SpecError(f"{what}: unknown mix keys {bad} (catalog §3)")
    if any(float(w) <= 0 for w in mix.values()):
        raise SpecError(f"{what}: mix weights must be > 0")
    return {k: float(w) for k, w in mix.items()}


def _activity(activity, device: str, what: str) -> None:
    if activity not in catalog.ACTIVITIES:
        raise SpecError(f"{what}: unknown activity '{activity}'")
    if not catalog.role_ok(activity, device):
        raise SpecError(f"{what}: catalog §2 runs {activity} on {catalog.ACTIVITIES[activity][0]}, not {device}")


def _default_duration(activity: str, what: str) -> Dist:
    default = catalog.default_duration(activity)
    if default is None:
        raise SpecError(f"{what}: {activity} runs 'as block' and needs `duration`")
    return Dist("uniform", (float(default[0]), float(default[1])), DURATION)


def _steps(steps, device: str, what: str) -> tuple[Step, ...]:
    if not isinstance(steps, list) or not steps:
        raise SpecError(f"{what}: sequence must be a list of steps")
    out = []
    for i, st in enumerate(steps):
        w = f"{what} step {i + 1}"
        unknown = set(st) - STEP_KEYS
        if unknown:
            raise SpecError(f"{w}: unknown keys {sorted(unknown)}")
        act = st.get("activity")
        _activity(act, device, w)
        if act in catalog.CALLS:
            raise SpecError(f"{w}: calls cannot be sequence steps")
        p = float(st.get("probability", 1.0))
        if not 0 < p <= 1:
            raise SpecError(f"{w}: probability must be in (0, 1]")
        out.append(Step(act, parse_duration(st["duration"]) if "duration" in st else _default_duration(act, w), p,
                        _mix(st.get("mix"), act, w), _opt_str(st, "pages"), _opt_str(st, "dwell"),
                        _opt_str(st, "lookups")))
    if all(st.probability < 1 for st in out):
        raise SpecError(f"{what}: at least one step needs probability 1, otherwise a sequence can be empty")
    return tuple(out)


def _opt_str(d: dict, key: str) -> str | None:
    if key not in d:
        return None
    if key == "lookups":   # drawn per plan row (planner), so it must be a count: 2, 1-3, Poisson(2)
        try:
            lo = parse(d[key], NUMBER).bounds()[0]
        except DistError as e:
            raise SpecError(f"lookups: {e}") from None
        if lo < 1:
            raise SpecError(f"lookups must be >= 1, got {d[key]}")
    return str(d[key])


def _block(d: dict, index: int, prof: dict) -> Block:
    what = f"block '{d.get('id')}'"
    _check_keys(d, BLOCK_KEYS, what)
    device = d.get("device")
    if device not in prof["devices"]:
        raise SpecError(f"{what}: device '{device}' is not one of {prof['devices']}")
    kinds = [k for k in ("activity", "split", "sequence") if k in d]
    if len(kinds) != 1:
        raise SpecError(f"{what}: give exactly one of activity / split / sequence, got {kinds}")
    activity = d.get("activity") or kinds[0]          # "split" / "sequence" for composite blocks
    if "activity" in d:
        _activity(activity, device, what)

    has = {k for k in ("at", "from", "to", "within") if k in d}
    if has == {"at"}:
        placement, at = "at", _time_ref(d["at"], what)
    elif has == {"from"}:
        placement, at = "from_duration", _time_ref(d["from"], what)
    elif has == {"from", "to"}:
        placement, at = "fill", _time_ref(d["from"], what)
    elif has == {"within"}:
        placement, at = "within", None
    else:
        raise SpecError(f"{what}: give exactly one of at / from (+duration) / from+to / within, got {sorted(has)}")
    if placement == "fill" and "duration" in d:
        raise SpecError(f"{what}: from+to fills the window, drop `duration`")
    within = None
    if placement == "within":
        w = d["within"]
        if not isinstance(w, list) or len(w) != 2:
            raise SpecError(f"{what}: within must be [start, end]")
        within = (_time_ref(w[0], what), _time_ref(w[1], what))

    split = sequence = None
    if "split" in d:
        if placement != "fill":
            raise SpecError(f"{what}: split needs from + to")
        parts = d["split"]
        if not isinstance(parts, dict) or not parts:
            raise SpecError(f"{what}: split must map activity -> share")
        for act in parts:
            _activity(act, device, f"{what} split")
            if act in catalog.CALLS or act in catalog.NEEDS_MIX:
                raise SpecError(f"{what}: split parts cannot be calls or need a mix ({act})")
        total = sum(float(x) for x in parts.values())
        split = tuple((a, float(x) / total) for a, x in parts.items())
    if "sequence" in d:
        if placement not in ("at", "within"):
            raise SpecError(f"{what}: a sequence needs at or within")
        if "duration" in d:
            raise SpecError(f"{what}: a sequence's duration is the sum of its steps")
        sequence = _steps(d["sequence"], device, what)

    duration = parse_duration(d["duration"]) if "duration" in d else None
    if duration is None and placement != "fill" and sequence is None:
        duration = _default_duration(activity, what)

    mix = _mix(d.get("mix"), activity, what) if "activity" in d else None
    if "mix" in d and "activity" not in d:
        raise SpecError(f"{what}: give mixes per step / use the default mix of each split activity")

    with_ = d.get("with")
    if with_ is not None and with_ not in catalog.COMPANIONS:
        raise SpecError(f"{what}: `with` supports {sorted(catalog.COMPANIONS)}, got '{with_}'")
    if with_ and not catalog.role_ok(with_, device):
        raise SpecError(f"{what}: {with_} cannot run on {device}")
    platform = d.get("platform")
    if activity in catalog.CALLS and platform not in catalog.CALL_PLATFORMS:
        raise SpecError(f"{what}: calls need platform in {sorted(catalog.CALL_PLATFORMS)}")
    if "lookups" in d and activity != "sh_adjacent_lookup":
        raise SpecError(f"{what}: lookups is only for sh_adjacent_lookup")
    if d.get("voice") and activity != "gaming_session":
        raise SpecError(f"{what}: voice is only for gaming_session")

    only = None
    if "only_if" in d:
        cond = d["only_if"]
        if not isinstance(cond, dict) or set(cond) != {"sleep_before"}:
            raise SpecError(f"{what}: only_if supports {{sleep_before: \"HH:MM\"}}")
        only = parse(cond["sleep_before"], TIME).bounds()[0]
    options = d.get("options")
    if options is not None:
        if not isinstance(options, dict) or not options:
            raise SpecError(f"{what}: options must be a mapping")
        options = ";".join(f"{k}={v}" for k, v in options.items())
    has_selector = bool(_SELECTOR_KEYS & set(d))
    if "replaces" in d and (has_selector or set(d) & {"count", *PERIOD_KEYS}):
        raise SpecError(f"{what}: a `replaces` block runs exactly on the replaced days; drop selectors/frequency")

    return Block(
        id=d["id"], index=index,
        selector=(_selector(d, prof["day_types"], prof.get("night_sets") or {}, what)
                  if "replaces" not in d else Selector()),
        freq=_freq(d, what), placement=placement, at=at,
        to=_time_ref(d["to"], what) if placement == "fill" else None,
        within=within, duration=duration, device=device, activity=activity, mix=mix,
        pages=_opt_str(d, "pages"), dwell=_opt_str(d, "dwell"), lookups=_opt_str(d, "lookups"),
        with_=with_, voice=bool(d.get("voice", False)), platform=platform,
        max_delay=parse_duration(d["max_delay"]).bounds()[1] if "max_delay" in d else DEFAULT_MAX_DELAY,
        min_gap=parse_duration(d["min_gap"]).bounds()[1] if "min_gap" in d else 0.0,
        not_before=_time_ref(d["not_before"], what) if "not_before" in d else None,
        night=bool(d.get("night", False)), group=d.get("group"), noise=bool(d.get("noise", True)),
        duration_scale=parse(d["duration_scale"], NUMBER) if "duration_scale" in d else None,
        only_sleep_before=only, replaces=d.get("replaces"), cancels=tuple(d.get("cancels") or ()),
        split=split, sequence=sequence, flag=d.get("flag"), options=options,
    )


def _away(d: dict, prof: dict) -> Away:
    what = f"away '{d.get('id')}'"
    _check_keys(d, AWAY_KEYS, what)
    if "from" not in d or ("to" in d) == ("length" in d):
        raise SpecError(f"{what}: needs from and exactly one of to / length")
    if d.get("replaces") not in (None, "evening"):
        raise SpecError(f"{what}: replaces supports only 'evening'")
    share = d.get("attend_share")
    if share is not None and not 0 <= float(share) <= 1:
        raise SpecError(f"{what}: attend_share must be in [0, 1]")
    if "skipped_allow" in d and share is None:
        raise SpecError(f"{what}: skipped_allow needs attend_share")
    if d.get("sleep_when_replaced") not in (None, "end"):
        raise SpecError(f"{what}: sleep_when_replaced supports only 'end'")
    if "sleep_when_replaced" in d and "keep_per_window" not in d:
        raise SpecError(f"{what}: sleep_when_replaced needs keep_per_window")
    return Away(
        id=d["id"], selector=_selector(d, prof["day_types"], prof.get("night_sets") or {}, what),
        freq=_freq(d, what), start=_time_ref(d["from"], what),
        end=_time_ref(d["to"], what) if "to" in d else None,
        length=_length(d["length"], what) if "length" in d else None,
        not_before=_time_ref(d["not_before"], what) if "not_before" in d else None,
        replaces=d.get("replaces"),
        sleep_after_return=parse_duration(d["sleep_after_return"]) if "sleep_after_return" in d else None,
        attend_share=float(share) if share is not None else None,
        skipped_allow=frozenset(d.get("skipped_allow") or ()),
        keep=parse(d["keep_per_window"], NUMBER) if "keep_per_window" in d else None,
        sleep_when_replaced="sleep_when_replaced" in d,
    )


def _length(value, what: str) -> Dist | str:
    if isinstance(value, str) and value.startswith("timetable."):
        return value
    try:
        return parse_duration(value)
    except DistError as e:
        raise SpecError(f"{what}: length: {e}") from None


def _anchor_rules(rules, prof: dict, what: str) -> list[AnchorRule]:
    out = []
    for i, r in enumerate(rules or []):
        w = f"{what}[{i}]"
        _check_keys(r, ANCHOR_KEYS, w)
        modifiers = {"shift", "sd_scale"} & set(r)
        if ("value" in r) == bool(modifiers):
            raise SpecError(f"{w}: give a value, or shift / sd_scale")
        if "unless_after" in r and "shift" not in r:
            raise SpecError(f"{w}: unless_after belongs to a shift")
        sel = _selector(r, prof["day_types"], prof.get("night_sets") or {}, w)
        out.append(AnchorRule(sel, parse(r["value"], TIME) if "value" in r else None,
                              parse_duration(r["shift"]) if "shift" in r else None,
                              float(r["sd_scale"]) if "sd_scale" in r else None, r.get("unless_after")))
    return out


def _build(raw: dict) -> Profile:
    for key in ("profile", "timezone", "devices", "day_types", "anchors", "blocks"):
        if key not in raw:
            raise SpecError(f"missing `{key}`")
    day_types = raw["day_types"]
    for name, days in day_types.items():
        bad = [x for x in days if x not in WEEKDAYS]
        if bad:
            raise SpecError(f"day type {name}: bad weekdays {bad}")
    for role in raw["devices"]:
        if role not in catalog.ROLES:
            raise SpecError(f"devices: unknown role '{role}'")

    tags: dict[str, tuple[int, str, str | None]] = {}
    tt = raw.get("timetable") or {}
    for tag, rule in (tt.get("tags") or {}).items():
        if rule.get("of") not in day_types:
            raise SpecError(f"timetable tag {tag}: unknown day type {rule.get('of')}")
        tags[tag] = (int(rule["choose"]), rule["of"], rule.get("else"))
    all_types = dict(day_types)
    for tag, (_, of, other) in tags.items():   # tags behave like day types in selectors
        all_types[tag] = day_types[of]
        if other:
            all_types[other] = day_types[of]
    values: dict[str, object] = {}
    for name, v in (tt.get("values") or {}).items():
        if isinstance(v, dict):
            for k in v:
                if k not in all_types and k not in WEEKDAYS:
                    raise SpecError(f"timetable value {name}: unknown key '{k}'")
            values[name] = {k: parse(x, TIME if ":" in str(x) else DURATION) for k, x in v.items()}
        else:
            values[name] = parse(v, TIME if ":" in str(v) else DURATION)

    raw = dict(raw, day_types=all_types)
    night_sets = {}
    for name, d in (raw.get("night_sets") or {}).items():
        f = _freq(d, f"night set {name}")
        if f.key != "per_week":
            raise SpecError(f"night set {name}: only per_week is supported")
        night_sets[name] = f

    anchors = raw["anchors"]
    wake = _anchor_rules(anchors.get("wake"), raw, "anchors.wake")
    sleep = _anchor_rules(anchors.get("sleep"), raw, "anchors.sleep")
    if not any(r.value for r in wake) or not any(r.value for r in sleep):
        raise SpecError("anchors need at least one wake and one sleep value")

    away = [_away(a, raw) for a in raw.get("away") or []]
    blocks = [_block(b, i, raw) for i, b in enumerate(raw["blocks"])]
    ids = [b.id for b in blocks] + [a.id for a in away]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise SpecError(f"duplicate ids {sorted(dupes)}")
    forbid = []
    for i, f in enumerate(raw.get("forbid") or []):
        _check_keys(f, {"within", "night"}, f"forbid[{i}]")
        forbid.append(Forbid(_time_ref(f["within"][0], "forbid"), _time_ref(f["within"][1], "forbid"),
                             bool(f.get("night", False))))

    noise = raw.get("noise") or {}
    if not isinstance(noise, dict) or set(noise) - {"duration"}:
        raise SpecError("noise: only {duration: <share>} is supported")
    duration_noise = float(noise.get("duration", 0.0))
    if not 0 <= duration_noise < 1:
        raise SpecError("noise.duration must be in [0, 1)")

    prof = Profile(
        name=raw["profile"], source=raw.get("source", ""), tier=int(raw.get("tier", 0)),
        extends=raw.get("extends"), root=raw["_root"], timezone=raw["timezone"],
        window_days=int(raw.get("window_days", 14)), warmup_days=int(raw.get("warmup_days", 1)),
        start_weekday=raw.get("start_weekday", "Mon"), devices=list(raw["devices"]),
        day_types=all_types, timetable_tags=tags, timetable_values=values,
        wake=wake, sleep=sleep, away=away, blocks=blocks, night_sets=night_sets, forbid=forbid,
        duration_noise=duration_noise,
    )
    _check_refs(prof)
    return prof


def _check_refs(prof: Profile) -> None:
    away = {a.id: a for a in prof.away}
    blocks = {b.id for b in prof.blocks}

    def check(ref: TimeRef | None, what: str) -> None:
        if ref is None or ref.name is None:
            return
        kind, _, rest = ref.name.partition(".")
        if kind == "timetable" and rest not in prof.timetable_values:
            raise SpecError(f"{what}: unknown {ref.name}")
        if kind in ("away", "replaced") and rest.split(".")[0] not in away:
            raise SpecError(f"{what}: unknown {ref.name}")
        if kind == "replaced" and away[rest.split(".")[0]].keep is None:
            raise SpecError(f"{what}: {ref.name} needs keep_per_window on that away period")

    for b in prof.blocks:
        for r in (b.at, b.to, b.not_before, *(b.within or ())):
            check(r, f"block '{b.id}'")
        if b.replaces is not None and (b.replaces not in away or away[b.replaces].keep is None):
            raise SpecError(f"block '{b.id}': replaces needs an away period with keep_per_window, got '{b.replaces}'")
        bad = [c for c in b.cancels if c not in blocks or c == b.id]
        if bad:
            raise SpecError(f"block '{b.id}': cancels unknown blocks {bad}")
    for a in prof.away:
        if isinstance(a.length, str) and a.length.split(".", 1)[1] not in prof.timetable_values:
            raise SpecError(f"away '{a.id}': unknown {a.length}")
        for r in (a.start, a.end, a.not_before):
            check(r, f"away '{a.id}'")
            if r is not None and r.name and r.name.split(".")[0] in ("away", "replaced"):
                raise SpecError(f"away '{a.id}': cannot refer to another away period")
        bad = [x for x in a.skipped_allow if x not in blocks]
        if bad:
            raise SpecError(f"away '{a.id}': skipped_allow names unknown blocks {bad}")
    for r in prof.wake + prof.sleep:
        if r.unless_after and r.unless_after not in blocks:
            raise SpecError(f"anchors: unless_after names unknown block '{r.unless_after}'")
