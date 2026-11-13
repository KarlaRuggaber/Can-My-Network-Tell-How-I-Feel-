"""What the synthesizer needs from the activity catalog (§2/§3) and the runner's mixes.yaml.

Keep in sync with profiles/activity-catalog.md and scheduler/scheduler/catalog.py.
"""

from __future__ import annotations

from pathlib import Path

S = 1_000_000  # µs per second

# How a block's planned duration is reached (README §3).
#   bounded: the duration is an upper bound, the activity ends on its own -> snippet as recorded, cut at duration
#   chain:   fill the duration; further bodies from any matching snippet, each with new client ports
#   loop:    fill the duration; the snippet's own body again, same ports (one continuous flow)
BOUNDED = {"crisis_resource_visit", "sh_adjacent_lookup", "messaging", "social_post"}   # + phone_check with pages
CHAIN = {"browse", "social_passive", "phone_check", "work_block", "study_block"}
LOOP = {"video_stream", "video_call", "voice_call", "gaming_session", "music_background", "repeat_visit_loop"}
# Ports change per copy for page activities (new connections); continuous flows keep them.
NEW_PORTS = CHAIN | {"repeat_visit_loop"}
NOTHING = {"idle_connected", "away"}            # no packets (runner sends nothing; away = no runs)

# Head = browser start and first page / call join / store pages; loops and chains repeat only the body.
HEAD_S = {"video_stream": 60, "video_call": 20, "voice_call": 20}
HEAD_DEFAULT_S = 30
HEAD_SHARE = {"gaming_session": 0.25}           # store pages are at most a quarter of the block (catalog §2)
MIN_BODY_S = 30                                 # a snippet with a shorter body is never chained or looped

# Category of an activity without a mix (scheduler: default mix key).
DEFAULT_CATEGORY = {
    "social_passive": "social_passive", "social_post": "social_post", "messaging": "messaging",
    "video_call": "call", "voice_call": "call", "video_stream": "streaming", "music_background": "audio",
    "work_block": "work", "study_block": "study", "gaming_session": "gaming", "crisis_resource_visit": "crisis_help",
}

# Hosts the runner reaches that mixes.yaml does not list as sites (README §1).
EXTRA_HOSTS = {
    "peer.sim": {"call", "gaming"},             # self-hosted Jitsi + WebSocket game (peer-vm/)
    "srg-ssr.ch": {"audio"},                    # MP3 fallback stream of music_background
    "srf.ch": {"audio", "streaming"},           # radio live pages; play.srf.ch redirects to www.srf.ch/play/tv
    "arxiv.org": {"study"},                     # study_block PDFs (documents.pdfs)
    "slack.com": {"messaging"},                 # messaging runs in the project's Slack (accounts.yaml)
    "reddit.com": {"social_post"},              # social_post: private r/CMNTHIF
}

COMPANION_SUFFIXES = ("-bg", "-voice")


def head_us(activity: str, duration_us: int) -> int:
    if activity in HEAD_SHARE:
        return int(duration_us * HEAD_SHARE[activity])
    return HEAD_S.get(activity, HEAD_DEFAULT_S) * S


def load_host_categories(mixes_yaml: str | Path | None) -> dict[str, set[str]]:
    """site host -> mix categories, from traffic-runner/config/mixes.yaml (PyYAML) plus EXTRA_HOSTS."""
    out: dict[str, set[str]] = {h: set(c) for h, c in EXTRA_HOSTS.items()}
    if mixes_yaml:
        import yaml
        data = yaml.safe_load(Path(mixes_yaml).read_text(encoding="utf-8"))
        for cat, spec in (data.get("categories") or {}).items():
            for site in spec.get("sites") or []:
                out.setdefault(site["host"].lower(), set()).add(cat)
        for stream in ((data.get("audio") or {}).get("streams") or []):
            out.setdefault(stream["host"].lower(), set()).add("audio")
    return out


def categories_of(hosts: list[str], activity: str, table: dict[str, set[str]],
                  recorded_mix: dict[str, float] | None = None) -> list[str]:
    """Mix categories a snippet actually loaded, one entry per known host (unknown hosts are skipped).

    A host in several categories (reddit.com: social_passive and social_post, srf.ch: audio and streaming) is
    narrowed to the activity's own category, else to the recorded mix."""
    cats: list[str] = []
    for host in hosts:
        host = host.strip().lower().rstrip(".")
        if not host:
            continue
        found: set[str] = set()
        for site, c in table.items():
            if host == site or host.endswith("." + site):
                found |= c
        if not found:
            continue
        own = DEFAULT_CATEGORY.get(activity)
        if own in found:
            found = {own}
        elif recorded_mix and found & set(recorded_mix):
            found &= set(recorded_mix)
        cats.append("|".join(sorted(found)))
    return cats


def parse_mix(text: str | None) -> dict[str, float]:
    """Runner/plan syntax 'news:0.4,messaging:0.4' or 'news,search' (equal weights) -> {key: weight}."""
    out: dict[str, float] = {}
    if not text:
        return out
    parts = [p.strip() for p in text.split(",") if p.strip()]
    for p in parts:
        key, _, w = p.partition(":")
        out[key.strip()] = float(w) if w else 1.0
    return {k: v for k, v in out.items() if v > 0}


def parse_options(text: str | None) -> dict[str, str]:
    """Plan `options` column, 'mic_share=0.1;x=y' (';' or ',' separated)."""
    out = {}
    for part in (text or "").replace(";", ",").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out
