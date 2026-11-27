"""HTTP API for the React UI. Reads the per-day cache only; it never computes metrics itself.

    uvicorn cmn_frontend.api:app --host 127.0.0.1 --port 8600

Every /api route except /api/health and /api/login needs a session (cookie set by /api/login).
A single-profile user sees only their own profile; a multi-profile user (clinician, parent) can
choose between their profiles and edit them (name, source, devices, baseline period).
"""

from __future__ import annotations

import math
import os
import statistics
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import assistant, auth, care as care_mod, fasl, llm, norms, observability, observed, setup_assist, speech as speech_mod
from . import sources as based_on   # the route function `sources` below would shadow the name
from .notes import NoteStore
from .groundtruth import blocks_on_day, day_summary, load_devices, load_plan, phase_by_day
from .personas import PHASE_LABEL, persona_meta
from .profiles import Device, Profile, ProfileStore, attention_summary
from .settings import PRODUCT_NAME, Settings, load_settings
from .store import DayStore

DEFAULT_BASELINE_DAYS = 14


@lru_cache(maxsize=1)
def _metric_labels(app_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    """dist_col -> label / criterion, from the thesis app's criterion definitions."""
    try:
        from .daily import load_metric_code
        code = load_metric_code(app_dir)  # type: ignore[arg-type]
        from .metric_names import plain_labels
        return plain_labels(code.labels.keys()), code.criterion_of
    except Exception:
        return {}, {}


def _baseline_stats(days: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Mean and SD of every metric over the complete baseline days (for trend bands)."""
    base = [d for d in days if d["phase"] == "baseline" and d["complete"]]
    keys = {k for d in base for k in d["metrics"]}
    out = {}
    for k in sorted(keys):
        vals = [d["metrics"][k] for d in base if isinstance(d["metrics"].get(k), (int, float))
                and not isinstance(d["metrics"].get(k), bool) and math.isfinite(d["metrics"][k])]
        if len(vals) >= 2:
            out[k] = {"mean": statistics.fmean(vals), "sd": statistics.stdev(vals), "n": len(vals)}
    return out


def _periods(profile: Profile, days: list[date], plan_phases: dict[str, str]) -> tuple[dict[date, str], dict]:
    """Phase per day ("baseline", "current", or outside) and each phase's planned span.

    Scripted sources take baseline and clinical phase from their plan. Other sources use the
    profile's baseline period (default: the first 14 days with data); every later day is "current".
    """
    if plan_phases:
        label = {d: PHASE_LABEL.get(p, p) for d, p in plan_phases.items()}
        first = min(plan_phases)
        out = {}
        for d in days:
            iso = d.isoformat()
            out[d] = label.get(iso) or ("pre-run" if iso < first else "post-run")
        spans = {}
        for ph in ("baseline", "current"):
            ds = sorted(x for x, p in label.items() if p == ph)
            spans[ph] = {"planned_first": ds[0] if ds else None, "planned_last": ds[-1] if ds else None,
                         "planned_days": len(ds)}
        return out, spans
    if profile.baseline_first and profile.baseline_last:
        b0, b1 = date.fromisoformat(profile.baseline_first), date.fromisoformat(profile.baseline_last)
    elif days:
        b0 = days[0]
        b1 = b0 + timedelta(days=DEFAULT_BASELINE_DAYS - 1)
    else:
        return {}, {}
    out = {d: "baseline" if b0 <= d <= b1 else ("current" if d > b1 else "before") for d in days}
    spans = {
        "baseline": {"planned_first": b0.isoformat(), "planned_last": b1.isoformat(),
                     "planned_days": (b1 - b0).days + 1},
        "current": {"planned_first": (b1 + timedelta(days=1)).isoformat(),
                    "planned_last": days[-1].isoformat() if days and days[-1] > b1 else None,
                    "planned_days": max(0, (days[-1] - b1).days) if days else 0},
    }
    return out, spans


def _hourly(activity: dict[str, Any] | None) -> list[int] | None:
    """Packets per hour of the day (24 values) from the 5-minute activity bins."""
    if not activity or not activity.get("total"):
        return None
    per = max(1, 60 // int(activity.get("bin_minutes") or 5))
    tot = activity["total"]
    return [int(sum(tot[h * per:(h + 1) * per])) for h in range(24)]


def profile_meta(p: Profile) -> dict[str, Any]:
    meta = persona_meta(p.persona) if p.persona else persona_meta("")
    return {**meta, "name": p.name, "id": p.id, "source": p.source,
            "scripted": bool(p.persona)}


def build_timeline(profile: Profile, settings: Settings, cfg: fasl.FaslConfig,
                   reference_source: str | None = None, age_band: str | None = None) -> dict[str, Any]:
    care = care_mod.CareStore(settings.home_dir).get(profile.id)
    clinical = care.get("clinical") or {}
    store = DayStore(settings.cache_dir)
    records = list(store.days(profile.cache_name))
    blocks = load_plan(settings.run_dir, profile.source)
    has_plan = bool(blocks)
    phase_of, spans = _periods(profile, [d for d, _ in records], phase_by_day(blocks))
    scores = fasl.score_days([r["metrics"] for _, r in records], cfg)

    days = []
    for i, ((day, rec), sc) in enumerate(zip(records, scores)):
        days.append({
            "date": day.isoformat(),
            "weekday": day.strftime("%a"),
            "phase": phase_of.get(day, "unknown"),
            "complete": i + 1 < len(records),   # a later day has data: the ingest moved on
            "n_partitions": rec.get("n_partitions"),
            "packets_kept": rec.get("packets_kept"),
            "first_packet": rec.get("first_packet"),
            "last_packet": rec.get("last_packet"),
            "computed_at": rec.get("computed_at"),
            "ground_truth": day_summary(blocks_on_day(blocks, day)) if has_plan else None,
            "metrics": {k: v for k, v in rec["metrics"].items() if k != "Date"},
            "hourly": _hourly(rec.get("activity")),
            "L": sc["L"],
            "parts": sc["parts"],
        })

    gate = cfg.gate
    configured = [c for c in fasl.CRIT_KEYS if cfg.configured(c)]
    # Default: the gate per phase, each on that phase's complete days only (as the evaluation's
    # score_phases). The rolling window mixes phases; it is an optional extra view.
    by_phase = {}
    for ph in ("baseline", "current"):
        sel = [d for d in days if d["phase"] == ph and d["complete"]]
        res = fasl.phase_gate({c: [d["L"][c] for d in sel] for c in configured}, gate)
        by_phase[ph] = {**res, **spans.get(ph, {"planned_first": None, "planned_last": None, "planned_days": 0}),
                        "counted": [d["date"] for d in sel][-gate.window:] if gate.window > 0 else [],
                        "in_progress": [d["date"] for d in days if d["phase"] == ph and not d["complete"]]}
    present = {c: fasl.gate_present_rolling([d["L"][c] for d in days], gate.theta, gate.need_days,
                                            gate.window)
               for c in configured}
    baseline_stats = _baseline_stats(days)
    labels, _ = _metric_labels(str(settings.app_dir))
    day_types = {d["date"]: care_mod.day_type(care.get("routine"), care.get("away_periods") or [], d["date"])
                 for d in days}
    obs = observed.build(days, [rec.get("activity") for _, rec in records], baseline_stats,
                         lambda k: labels.get(k, k),
                         reference=typical_reference(settings, profile, reference_source, age_band),
                         day_types=day_types, focus=clinical.get("focus"), normals=clinical.get("normals"),
                         changes=care_mod.change_flags_on(care.get("clinical")))   # one rule: the care plan's (K5)
    if obs.get("reference") is not None:
        obs["reference"]["available"] = list(REFERENCE_SOURCES)
    return {
        "profile": {**profile.to_json(), "has_plan": has_plan,
                    "phase_labels": {"baseline": "Baseline", "current": "Clinical" if has_plan else "Recent"}},
        "persona": profile_meta(profile),
        "status": "ready" if records else "pending",
        "days": days,
        "gate": {"params": {"theta": gate.theta, "N": gate.need_days, "M": gate.window,
                            "core": list(gate.core), "min_present": gate.min_present},
                 "phases": by_phase,
                 "rolling": {"present": present, "episode": fasl.episode_flags(present, gate),
                             "note": "rolling window over the last M days; mixes phases"}},
        "baseline_stats": baseline_stats,
        "observed": obs,
        "care": care,
    }


_REF_CACHE: dict[tuple, dict[str, list[float]]] = {}


def _reference_values(p: Profile, settings: Settings) -> dict[str, list[float]]:
    """Observed track values of one person's days that count as healthy reference (cached)."""
    folder = settings.cache_dir / p.cache_name
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    key = (p.cache_name, p.reference_mode, p.baseline_first, p.baseline_last, observed.active_packets(),
           len(files), max((f.stat().st_mtime for f in files), default=0.0))
    if key in _REF_CACHE:
        return _REF_CACHE[key]
    records = list(DayStore(settings.cache_dir).days(p.cache_name))
    phase_of, _ = _periods(p, [d for d, _ in records], phase_by_day(load_plan(settings.run_dir, p.source)))
    days = [{"date": day.isoformat(), "phase": phase_of.get(day, "unknown"), "complete": i + 1 < len(records),
             "packets_kept": rec.get("packets_kept"), "metrics": rec.get("metrics", {})}
            for i, (day, rec) in enumerate(records)]
    observed.build(days, [rec.get("activity") for _, rec in records], {})
    mode = p.reference_mode
    vals = observed.track_values(
        days, lambda d: d["complete"] and d["observed"]["has_data"] and (mode == "all" or d["phase"] == "baseline"))
    _REF_CACHE[key] = vals
    return vals


def healthy_reference(settings: Settings, viewed: Profile, with_values: bool = False) -> dict[str, Any] | None:
    """Pooled days of the other people in the reference group (never the viewed person's own source).

    By default the scripted personas' baseline days: they live a healthy everyday profile
    (profiles/tier0-healthy) before their clinical phase. Healthy volunteers can be added by
    setting a person's healthy reference to "all days".
    """
    pooled: dict[str, list[float]] = {}
    people, n_days = [], 0
    for p in ProfileStore(settings).all():
        if p.reference_mode == "none" or p.source == viewed.source:
            continue
        vals = _reference_values(p, settings)
        if not vals:
            continue
        people.append(p.name)
        n_days += max(len(v) for v in vals.values())
        for k, v in vals.items():
            pooled.setdefault(k, []).extend(v)
    stats = observed.reference_stats(pooled)
    if not stats:
        return None
    return {"stats": stats, "n_days": n_days, "people": people, **({"values": pooled} if with_values else {})}


REFERENCE_SOURCES = ("pooled", "external")


def reference_source_default() -> str:
    src = os.environ.get("CMN_REFERENCE_SOURCE", "pooled")
    return src if src in REFERENCE_SOURCES else "pooled"


def typical_reference(settings: Settings, viewed: Profile, source: str | None = None,
                      age_band: str | None = None) -> dict[str, Any] | None:
    """The typical (reference-group) range for the viewed person, from the chosen source.

    "pooled" (default): other people's usual days, empirical percentiles. "external": published
    norms for the behaviours our metrics stand in for (norms.json), by age band, normal assumption.
    """
    source = source if source in REFERENCE_SOURCES else reference_source_default()
    if source == "external":
        return norms.external_reference(age_band)
    pooled = healthy_reference(settings, viewed, with_values=True)
    if not pooled:
        return None
    return observed.pooled_reference(pooled["values"], pooled["n_days"], pooled["people"])


_ATTENTION_CACHE: dict[str, tuple[tuple, dict[str, Any]]] = {}


def _mtime(path: Any) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def profile_attention(p: Profile, settings: Settings, cfg_fn: Any, seen: dict[str, Any]) -> dict[str, Any]:
    """{flags, alert} for the person list: open risk flags and whether a crisis/self-harm flag is on.

    Cached until the person's day records, the care plan, the notes, the profiles or the FASL config
    change, so a list of many people does not rebuild every timeline on each request.
    """
    folder = settings.cache_dir / p.cache_name
    files = sorted(folder.glob("*.json")) if folder.is_dir() else []
    home = settings.home_dir
    key = (repr(p.to_json()), len(files), max((_mtime(f) for f in files), default=0.0),
           _mtime(home / "care.json"), _mtime(home / "notes.json"), _mtime(home / "profiles.json"),
           _mtime(settings.fasl_config), observed.active_packets(), reference_source_default(), norms.age_band())
    hit = _ATTENTION_CACHE.get(p.id)
    if hit and hit[0] == key:
        return hit[1]
    if not files:
        out = {"flags": 0, "alert": False}
    else:
        tl = build_timeline(p, settings, cfg_fn())
        out = attention_summary(tl["observed"]["flags"], seen)
    _ATTENTION_CACHE[p.id] = (key, out)
    return out


def for_person(tl: dict[str, Any]) -> dict[str, Any]:
    """What a single-profile user (the person themself) may see.

    No expected outcomes, condition, persona description or scripted plan, so the view cannot
    suggest symptoms (no expectation or placebo effect). The second period is called "Recent".
    """
    tl = dict(tl)
    tl["persona"] = {"id": tl["persona"]["id"], "name": tl["persona"]["name"], "source": "",
                     "scripted": False, "condition": "", "summary": "", "profile": None,
                     "baseline_profile": None, "expected": {}, "episode": None}
    tl["profile"] = {**tl["profile"], "persona": None, "has_plan": False, "source": "",
                     "devices": [{"ip": "", "label": f"Device {i + 1}"} for i in range(len(tl["profile"]["devices"]))],
                     "phase_labels": {"baseline": "Usual weeks", "current": "Recent"}}
    # Raw metrics of every criterion are not needed for the person's view, and some (crisis lines,
    # self-harm sites) must not reach their browser at all; the scored criteria's parts stay.
    tl["days"] = [{**d, "ground_truth": None, "metrics": {},
                   "observed": dict(d["observed"]) if "observed" in d else None} for d in tl["days"]]
    unscored = ("C3_", "C5_", "C6_", "C7_", "C9_")
    tl["baseline_stats"] = {k: v for k, v in tl.get("baseline_stats", {}).items() if not k.startswith(unscored)}
    if "observed" in tl:
        tl["observed"] = {**tl["observed"], "flags": list(tl["observed"]["flags"]), "focus": {}}
        observed.for_person(tl["observed"], tl["days"])
    if "care" in tl:     # the person sees their own routine and away periods, not the clinical setup
        tl["care"] = {"routine": tl["care"].get("routine"), "away_periods": tl["care"].get("away_periods", []),
                      "clinical": None, "updated": {k: v for k, v in tl["care"].get("updated", {}).items() if k != "clinical"}}
    return tl


class ChatMessage(BaseModel):
    role: str
    content: str


class NoteBody(BaseModel):
    date: str
    text: str


class SeenBody(BaseModel):
    last_day: str


class RoutineBody(BaseModel):
    routine: dict[str, Any]


class AwayBody(BaseModel):
    away_periods: list[dict[str, Any]]


class ClinicalBody(BaseModel):
    clinical: dict[str, Any]


class SuggestBody(BaseModel):
    kind: str                       # "routine" | "focus"
    text: str = ""


class AssistantBody(BaseModel):
    messages: list[ChatMessage]
    focus: str | None = None


class AssistantSettingsBody(BaseModel):
    enabled: bool
    model: str
    api_key: str | None = None      # None: keep the stored key; "": remove it
    provider: str | None = None     # "anthropic" | "local"; None: keep the current one
    base_url: str | None = None     # local: OpenAI-compatible endpoint; None: keep
    fallback: bool | None = None    # local: Claude answers when the local model is unreachable; None: keep


class AssistantCheckBody(BaseModel):
    base_url: str
    model: str


class LoginBody(BaseModel):
    username: str
    password: str


class DeviceBody(BaseModel):
    ip: str
    label: str = ""


class ProfileBody(BaseModel):
    id: str | None = None
    name: str
    source: str
    all_devices: bool = True
    devices: list[DeviceBody] = []
    baseline_first: str | None = None
    baseline_last: str | None = None
    reference: str | None = None       # healthy reference: none | baseline | all


def create_app(settings: Settings | None = None, llm_client: Any = None,
               speech_transport: Any = None) -> FastAPI:
    settings = settings or load_settings()
    assistant_cfg = assistant.AssistantConfig(settings.home_dir)
    app = FastAPI(title=f"{PRODUCT_NAME} – results API")
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    users = auth.UserStore(settings.home_dir)
    profiles = ProfileStore(settings)
    notes = NoteStore(settings.home_dir)
    carestore = care_mod.CareStore(settings.home_dir)
    speech = speech_mod.Speech(transport=speech_transport)

    def config() -> fasl.FaslConfig:
        return fasl.load_config(settings.fasl_config)  # re-read: edits apply without restart

    def current_user(request: Request) -> auth.User:
        name = auth.read_session(settings.home_dir, request.cookies.get(auth.SESSION_COOKIE))
        user = users.get(name) if name else None
        if user is None:
            raise HTTPException(401, "please log in")
        return user

    def multi_user(user: auth.User = Depends(current_user)) -> auth.User:
        if user.role != "multi":
            raise HTTPException(403, "only for multi-profile users")
        return user

    def visible(user: auth.User) -> list[Profile]:
        return [p for p in profiles.all() if user.can_see(p.id)]

    def profile_for(user: auth.User, pid: str) -> Profile:
        p = profiles.get(pid)
        if p is None or not user.can_see(pid):
            raise HTTPException(404, f"no profile {pid}")
        return p

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "cache_dir": str(settings.cache_dir),
                "datasets": DayStore(settings.cache_dir).datasets(),
                "has_users": bool(users.all())}

    @app.post("/api/login")
    def login(body: LoginBody, response: Response) -> dict[str, Any]:
        user = users.verify(body.username.strip(), body.password)
        if user is None:
            raise HTTPException(401, "Invalid login data")
        response.set_cookie(auth.SESSION_COOKIE, auth.make_session(settings.home_dir, user.username),
                            max_age=auth.SESSION_SECONDS, httponly=True, samesite="strict",
                            secure=os.environ.get("CMN_COOKIE_SECURE", "") in ("1", "true", "yes"))
        return user.public()

    @app.post("/api/logout")
    def logout(response: Response) -> dict[str, bool]:
        response.delete_cookie(auth.SESSION_COOKIE)
        return {"ok": True}

    @app.get("/api/me")
    def me(user: auth.User = Depends(current_user)) -> dict[str, Any]:
        return user.public()

    @app.get("/api/config")
    def get_config(user: auth.User = Depends(current_user)) -> dict[str, Any]:
        labels, crit_of = _metric_labels(str(settings.app_dir))
        cfg = config()
        configured = [c for c in fasl.CRIT_KEYS if cfg.configured(c)]
        extra = {} if user.role == "single" else {
            "observability": observability.table(configured), "risk_criteria": observability.RISK_CRITERIA,
            "risks": [{"id": r.id, "title": r.title, "track": r.track} for r in observed.RISKS]
                     + [{"id": "sensitive_sites", "title": "Crisis or self-harm sites", "track": "sensitive_days"}],
        }
        return {**cfg.to_json(), **extra, "criterion_names": fasl.CRIT_NAMES,
                "metric_labels": labels, "metric_criterion": crit_of,
                "fasl_config_path": str(settings.fasl_config)}

    @app.get("/api/profiles")
    def list_profiles(user: auth.User = Depends(current_user)) -> list[dict[str, Any]]:
        store = DayStore(settings.cache_dir)
        out = []
        for p in visible(user):
            days = [d for d, _ in store.days(p.cache_name)]
            meta = profile_meta(p)
            person = user.role == "single"
            cfg_json = p.to_json()
            if person:     # source and device names of scripted runs name the condition
                cfg_json.update(source="", persona=None,
                                devices=[{"ip": "", "label": f"Device {i + 1}"} for i in range(len(p.devices))])
            out.append({"id": p.id, "name": p.name, "condition": "" if person else meta["condition"],
                        "source": "" if person else p.source, "scripted": False if person else meta["scripted"], "n_days": len(days), "config": cfg_json,
                        "first_day": days[0].isoformat() if days else None,
                        "last_day": days[-1].isoformat() if days else None,
                        **({} if person else {"attention": _attention(p)})})
        return out

    def _attention(p: Profile) -> dict[str, Any]:
        try:
            return profile_attention(p, settings, config, notes.seen(p.id))
        except Exception:     # a broken day record must not break the person list
            return {"flags": 0, "alert": False}

    @app.get("/api/profiles/{pid}")
    def timeline(pid: str, reference: str | None = None, age_band: str | None = None,
                 user: auth.User = Depends(current_user)) -> dict[str, Any]:
        if reference is not None and reference not in REFERENCE_SOURCES:
            raise HTTPException(400, f"reference must be one of {', '.join(REFERENCE_SOURCES)}")
        if age_band is not None and age_band not in norms.AGE_BANDS:
            raise HTTPException(400, f"age_band must be one of {', '.join(norms.AGE_BANDS)}")
        tl = build_timeline(profile_for(user, pid), settings, config(), reference, age_band)
        if user.role == "single":
            return for_person(tl)
        return {**tl, "notes": notes.notes(pid), "seen": notes.seen(pid)}

    # ---- onboarding and care plan ----

    def _care_out(user: auth.User, pid: str) -> dict[str, Any]:
        c = carestore.get(pid)
        if user.role == "multi":
            return c
        out = {**c, "clinical": None}       # the purpose is part of the clinical setup
        for k in ("purpose", "change_flags"):
            out.pop(k, None)
        return out

    @app.put("/api/profiles/{pid}/care/routine")
    def put_routine(pid: str, body: RoutineBody, user: auth.User = Depends(current_user)) -> dict[str, Any]:
        profile_for(user, pid)       # the person edits their own routine; links stay with clinicians
        try:
            carestore.set_routine(pid, body.routine, user.username, keep_links=user.role == "single")
        except ValueError as e:
            raise HTTPException(422, str(e))
        return _care_out(user, pid)

    @app.put("/api/profiles/{pid}/care/away")
    def put_away(pid: str, body: AwayBody, user: auth.User = Depends(current_user)) -> dict[str, Any]:
        profile_for(user, pid)
        try:
            carestore.set_away(pid, body.away_periods, user.username)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return _care_out(user, pid)

    @app.put("/api/profiles/{pid}/care/clinical")
    def put_clinical(pid: str, body: ClinicalBody, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        profile_for(user, pid)
        try:
            carestore.set_clinical(pid, body.clinical, user.username,
                                   [r.id for r in observed.RISKS] + ["sensitive_sites"],
                                   [t.key for t in observed.TRACKS])
        except ValueError as e:
            raise HTTPException(422, str(e))
        return _care_out(user, pid)

    @app.post("/api/profiles/{pid}/setup-suggestion")
    def setup_suggestion(pid: str, body: SuggestBody, user: auth.User = Depends(current_user)) -> dict[str, Any]:
        profile_for(user, pid)
        st = assistant_cfg.load()
        if not st["enabled"]:
            raise HTTPException(503, "The assistant is turned off (Settings → Assistant).")
        clients = {"client": llm_client}
        try:
            if body.kind == "routine":
                if not body.text.strip():
                    raise ValueError("describe the week first")
                return {"routine": setup_assist.suggest_routine(st, body.text[:4000], **clients)}
            if body.kind == "focus":
                if user.role != "multi":
                    raise HTTPException(403, "only for clinicians and parents")
                c = carestore.get(pid)
                notes_text = {k: (c.get("clinical") or {}).get(k, "") for k in ("history", "concerns", "treatment")}
                if body.text.strip():
                    notes_text["additional"] = body.text[:4000]
                if not any(v.strip() for v in notes_text.values()):
                    raise ValueError("enter the history or concerns first")
                risks = [{"id": r.id, "title": r.title} for r in observed.RISKS] + \
                        [{"id": "sensitive_sites", "title": "Crisis or self-harm sites"}]
                return {"focus": setup_assist.suggest_focus(st, notes_text, c.get("routine"), risks, **clients)}
        except ValueError as e:
            raise HTTPException(422, str(e))
        raise HTTPException(400, "kind must be routine or focus")

    # ---- notes and flags marked as seen (clinicians and parents) ----

    def _valid_day(day: str) -> str:
        try:
            return date.fromisoformat(day).isoformat()
        except ValueError:
            raise HTTPException(400, "day must be YYYY-MM-DD")

    @app.post("/api/profiles/{pid}/notes")
    def add_note(pid: str, body: NoteBody, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        profile_for(user, pid)
        try:
            notes.add(pid, _valid_day(body.date), body.text, user.username)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return {"notes": notes.notes(pid)}

    @app.delete("/api/profiles/{pid}/notes/{note_id}")
    def delete_note(pid: str, note_id: str, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        profile_for(user, pid)
        if not notes.delete(pid, note_id):
            raise HTTPException(404, "no such note")
        return {"notes": notes.notes(pid)}

    @app.put("/api/profiles/{pid}/flags/{flag_id}/seen")
    def mark_seen(pid: str, flag_id: str, body: SeenBody, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        profile_for(user, pid)
        notes.mark_seen(pid, flag_id[:40], _valid_day(body.last_day), user.username)
        return {"seen": notes.seen(pid)}

    @app.delete("/api/profiles/{pid}/flags/{flag_id}/seen")
    def unmark_seen(pid: str, flag_id: str, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        profile_for(user, pid)
        notes.unmark_seen(pid, flag_id[:40])
        return {"seen": notes.seen(pid)}

    @app.get("/api/profiles/{pid}/days/{day}")
    def day_detail(pid: str, day: str, user: auth.User = Depends(current_user)) -> dict[str, Any]:
        p = profile_for(user, pid)
        try:
            d = date.fromisoformat(day)
        except ValueError:
            raise HTTPException(400, "day must be YYYY-MM-DD")
        rec = DayStore(settings.cache_dir).load(p.cache_name, d)
        if rec is None:
            raise HTTPException(404, f"no data for {pid} on {day}")
        blocks = [] if user.role == "single" else blocks_on_day(load_plan(settings.run_dir, p.source), d)
        activity = rec.get("activity")
        if user.role == "single" and activity:
            activity = {k: v for k, v in activity.items() if k != "site_visits"}   # never crisis sites for the person
            activity["devices"] = {f"Device {i + 1}": v for i, v in enumerate(activity.get("devices", {}).values())}
        return {"profile": pid, "date": day, "activity": activity,
                "blocks": [b.to_json() for b in blocks],
                "packets_raw": rec.get("packets_raw"), "packets_kept": rec.get("packets_kept"),
                "n_partitions": rec.get("n_partitions"),
                "last_partition_start": rec.get("last_partition_start")}

    # ---- dictation: local speech to text (Whisper on this machine) ----

    @app.get("/api/transcribe")
    async def transcribe_status(user: auth.User = Depends(current_user)) -> dict[str, Any]:
        return await speech.status()

    @app.post("/api/transcribe")
    async def transcribe(request: Request, user: auth.User = Depends(current_user)) -> dict[str, Any]:
        size = request.headers.get("content-length")
        if size and size.isdigit() and int(size) > speech_mod.MAX_AUDIO_BYTES:
            raise HTTPException(413, "The recording is too long.")
        audio = await request.body()
        if not audio:
            raise HTTPException(400, "No recording received.")
        if len(audio) > speech_mod.MAX_AUDIO_BYTES:
            raise HTTPException(413, "The recording is too long.")
        ctype = request.headers.get("content-type", "")
        if not (ctype.startswith("audio/") or ctype.startswith("video/webm") or ctype == "application/octet-stream"):
            raise HTTPException(415, "Not an audio recording.")
        try:
            return await speech.transcribe(audio, ctype)
        except speech_mod.SpeechError as e:
            raise HTTPException(e.status, str(e))

    # ---- explanation assistant ----

    @app.get("/api/assistant")
    def assistant_status(user: auth.User = Depends(current_user)) -> dict[str, Any]:
        pub = assistant_cfg.public()
        pub["enabled"] = pub["enabled"] and pub["has_key"]
        if user.role != "multi":
            pub = {k: pub[k] for k in ("enabled", "notice")}
        return pub

    @app.put("/api/assistant")
    def assistant_settings(body: AssistantSettingsBody, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        try:
            assistant_cfg.save(body.enabled, body.model, body.api_key, body.provider, body.base_url, body.fallback)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return assistant_cfg.public()

    @app.post("/api/assistant/check")
    def assistant_check(body: AssistantCheckBody, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        """Local provider: is the endpoint reachable from this server and does it serve the model?"""
        try:
            url = llm.check_base_url(body.base_url)
        except ValueError as e:
            raise HTTPException(422, str(e))
        c = assistant_cfg.load()
        key = c["api_key"] if c["provider"] == "local" else ""
        return llm.check_local(url, body.model.strip(), key, client=llm_client)

    def _assistant_context(pid: str, user: auth.User) -> tuple[dict[str, Any], bool, dict[str, str]]:
        """The data the assistant gets for this page (the same for a question and for the warm-up)."""
        p = profile_for(user, pid)
        person = user.role == "single"
        tl = build_timeline(p, settings, config())
        if person:
            tl = for_person(tl)
        else:
            tl["notes"] = notes.notes(pid)
        if not tl["days"]:
            raise HTTPException(409, "No data for this profile yet.")
        labels, _ = _metric_labels(str(settings.app_dir))
        return assistant.build_context(tl, config(), person, labels), person, labels

    @app.post("/api/profiles/{pid}/assistant/warm")
    def warm(pid: str, user: auth.User = Depends(current_user)) -> dict[str, Any]:
        """Local model only: read this page's data now, in the background, so the first question is fast."""
        st = assistant_cfg.load()
        if not st["enabled"] or st.get("provider") != "local":
            return {"warm": "not_local"}
        ctx, person, _ = _assistant_context(pid, user)
        return {"warm": llm.warm_local(st, assistant.system_blocks(ctx, person), client=llm_client)}

    @app.post("/api/profiles/{pid}/assistant")
    def ask(pid: str, body: AssistantBody, user: auth.User = Depends(current_user)) -> StreamingResponse:
        st = assistant_cfg.load()
        if not st["enabled"]:
            raise HTTPException(503, "The assistant is turned off (Settings → Assistant).")
        ctx, person, labels = _assistant_context(pid, user)
        try:
            msgs = assistant.clean_messages([m.model_dump() for m in body.messages], body.focus)
        except ValueError as e:
            raise HTTPException(422, str(e))
        chunks = assistant.stream_answer(st, assistant.system_blocks(ctx, person), msgs,
                                         client=llm_client)
        # The hidden <based_on> block never reaches the text; one record follows it (sources.py).
        # Safety net: no clinical terms reach the person, whatever the model writes (visible text only).
        chunks = based_on.answer_stream(chunks, ctx, person, body.focus, labels,
                                       guard=assistant.guard_person if person else None)
        return StreamingResponse(chunks, media_type="text/plain; charset=utf-8",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    # ---- configuration (multi-profile users) ----

    @app.get("/api/sources")
    def sources(user: auth.User = Depends(multi_user)) -> list[dict[str, Any]]:
        store = DayStore(settings.cache_dir)
        out = []
        for src in profiles.sources():
            days = [d for d, _ in store.days(src)]
            out.append({"source": src, "n_days": len(days),
                        "first_day": days[0].isoformat() if days else None,
                        "last_day": days[-1].isoformat() if days else None,
                        "has_plan": (settings.run_dir / f"{src}.csv").is_file()})
        return out

    @app.get("/api/sources/{source}/devices")
    def source_devices(source: str, user: auth.User = Depends(multi_user)) -> list[dict[str, Any]]:
        """Local IP addresses seen in a source (from the whole-source day records), with labels."""
        if source not in profiles.sources():
            raise HTTPException(404, f"no source {source}")
        totals: dict[str, int] = {}
        seen_days: dict[str, int] = {}
        last_seen: dict[str, str] = {}
        for day, rec in DayStore(settings.cache_dir).days(source):
            for ip, n in (rec.get("local_ips") or {}).items():
                totals[ip] = totals.get(ip, 0) + int(n)
                seen_days[ip] = seen_days.get(ip, 0) + 1
                last_seen[ip] = day.isoformat()
        known = {ip: d for ip, d in load_devices(settings.devices_csv).items()}
        assigned: dict[str, list[str]] = {}
        for p in profiles.all():
            if p.source == source and not p.all_devices:
                for ip in p.device_ips:
                    assigned.setdefault(ip, []).append(p.name)
        labels = {d.ip: d.label for p in profiles.all() if p.source == source for d in p.devices if d.label}
        ips = sorted(set(totals) | {ip for ip, d in known.items() if d.get("dataset") == source},
                     key=lambda ip: -totals.get(ip, 0))
        return [{"ip": ip, "packets": totals.get(ip, 0), "days": seen_days.get(ip, 0),
                 "last_seen": last_seen.get(ip),
                 "label": labels.get(ip) or known.get(ip, {}).get("device", ""),
                 "role": known.get(ip, {}).get("role", ""),
                 "assigned_to": assigned.get(ip, [])} for ip in ips]

    def _save(body: ProfileBody, pid: str, old: Profile | None) -> dict[str, Any]:
        p = Profile(id=pid, name=body.name.strip(), source=body.source, all_devices=body.all_devices,
                    devices=[Device(d.ip.strip(), d.label.strip()) for d in body.devices],
                    baseline_first=body.baseline_first or None, baseline_last=body.baseline_last or None,
                    persona=old.persona if old and old.source == body.source else None,
                    reference=body.reference or None)
        try:
            profiles.upsert(p)
        except ValueError as e:
            raise HTTPException(422, str(e))
        pending = not any(True for _ in DayStore(settings.cache_dir).days(p.cache_name))
        return {**p.to_json(), "pending": pending}

    @app.post("/api/profiles")
    def create_profile(body: ProfileBody, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        pid = (body.id or body.name).strip().lower().replace(" ", "-")
        if profiles.get(pid):
            raise HTTPException(409, f"profile {pid} exists")
        out = _save(body, pid, None)
        if "*" not in user.profiles:      # a parent who adds a person can see that person
            users.grant(user.username, pid)
        return out

    @app.put("/api/profiles/{pid}")
    def update_profile(pid: str, body: ProfileBody, user: auth.User = Depends(multi_user)) -> dict[str, Any]:
        old = profile_for(user, pid)
        return _save(body, pid, old)

    @app.delete("/api/profiles/{pid}")
    def delete_profile(pid: str, user: auth.User = Depends(multi_user)) -> dict[str, bool]:
        profile_for(user, pid)
        return {"ok": profiles.delete(pid)}

    if settings.web_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dist, html=True), name="web")
    return app


app = create_app()
