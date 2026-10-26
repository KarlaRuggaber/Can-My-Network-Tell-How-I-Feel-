"""video_stream: play a video until it ends or the block ends (catalog §2), at the lowest
quality the player allows (hotspot uplink).

YouTube: one of the first results of a search term from mixes.yaml (144p preference).
SRF: one of the first on-demand videos on the SRF Play overview (lowest of its quality
levels, usually 180p). SRF live TV is not used: its player exposes no quality levels and
would stream at 540p. No video IDs are hard-coded, so nothing goes stale.

Stalls: when the video stops playing for about 45 s (three bad checks), the runner reloads the
same video once, then switches to other videos, at most MAX_RECOVERIES times per block. Asked
for after the pilot of 23.10: a YouTube stall with four browsers on the hotspot left 29 minutes
of a block silent. The replacement videos are drawn up front, so the seed still fixes the run.
"""

import logging

from ..context import MediaStalled, PageError

log = logging.getLogger(__name__)

ID = "video_stream"
IMPLEMENTED = True
ROLES = ("phone", "laptop")
DEFAULT_DURATION = (1800, 7200)
NEEDS_MIX = True
DEFAULT_MIX = "streaming"
MIX_KIND = "video"
NEEDS_BROWSER = True

SRF_START_URL = "https://www.srf.ch/play/tv"
MAX_RECOVERIES = 4  # per block: reload the same video once, then up to three other videos
RETRY_PAUSE = 10.0  # seconds between a stall and the restart


def run(ctx, rng, duration, mix):
    site = mix.pick(rng, ctx.hung_sites)
    terms = ctx.mixes.video.get("youtube_search_terms") or []
    pool = int(ctx.mixes.video.get("result_pool", 5))

    def draw():
        return (rng.choice(terms) if terms else "dokumentation"), rng.randrange(pool)

    first = draw()
    others = [draw() for _ in range(MAX_RECOVERIES - 1)]  # up front: no draws after network
    plan = [first, first, *others]  # start, reload the same video, then other videos
    for attempt, (term, result_index) in enumerate(plan):
        last = attempt == len(plan) - 1
        if attempt:
            ctx.idle(min(RETRY_PAUSE, ctx.remaining()))
            if ctx.remaining() <= 0:
                break
            log.warning("restarting video (%s of %d): %s", attempt, MAX_RECOVERIES,
                        "same video" if attempt == 1 else "another video")
        try:
            _play(ctx, site, term, result_index, ctx.mixes.video.get("srf_start_url", SRF_START_URL))
        except PageError as e:
            if attempt == 0 or last:
                raise
            log.warning("restart failed: %s", e)  # counts as one recovery
            continue
        try:
            ctx.watch_media()
            break
        except MediaStalled as e:
            if last:
                raise
            log.warning("%s after %.0f s", e, ctx.elapsed())
    return ctx.visited


def _play(ctx, site, term, result_index, srf_start_url):
    if site.host.endswith("youtube.com"):
        ctx.play_youtube(term, result_index)
    elif site.host.endswith("srf.ch"):
        ctx.play_srf(srf_start_url, result_index)
    else:
        raise PageError(f"no player implemented for {site.host}")
