"""video_stream: play a video until it ends or the block ends (catalog §2), at the lowest
quality the player allows (hotspot uplink).

YouTube: one of the first results of a search term from mixes.yaml (144p preference).
SRF: one of the first on-demand videos on the SRF Play overview (lowest of its quality
levels, usually 180p). SRF live TV is not used: its player exposes no quality levels and
would stream at 540p. No video IDs are hard-coded, so nothing goes stale.
"""

from ..context import PageError

ID = "video_stream"
IMPLEMENTED = True
ROLES = ("phone", "laptop")
DEFAULT_DURATION = (1800, 7200)
NEEDS_MIX = True
DEFAULT_MIX = "streaming"
MIX_KIND = "video"
NEEDS_BROWSER = True

SRF_START_URL = "https://www.srf.ch/play/tv"


def run(ctx, rng, duration, mix):
    site = mix.pick(rng)
    terms = ctx.mixes.video.get("youtube_search_terms") or []
    term = rng.choice(terms) if terms else "dokumentation"
    result_index = rng.randrange(int(ctx.mixes.video.get("result_pool", 5)))
    if site.host.endswith("youtube.com"):
        ctx.play_youtube(term, result_index)
    elif site.host.endswith("srf.ch"):
        ctx.play_srf(ctx.mixes.video.get("srf_start_url", SRF_START_URL), result_index)
    else:
        raise PageError(f"no player implemented for {site.host}")
    ctx.watch_media()
    return ctx.visited
