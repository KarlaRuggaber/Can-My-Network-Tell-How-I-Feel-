"""video_stream: play a video until it ends or the block ends (catalog §2), at the lowest
quality the player allows (hotspot uplink).

Only YouTube is playable: play.srf.ch streams H.264/AAC, which Playwright's Chromium cannot
decode (marked `playable: false` in mixes.yaml). The video is one of the first results of
a search term from mixes.yaml, so no video IDs are hard-coded.
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


def run(ctx, rng, duration, mix):
    site = mix.pick(rng)
    terms = ctx.mixes.video.get("youtube_search_terms") or []
    term = rng.choice(terms) if terms else "dokumentation"
    result_index = rng.randrange(int(ctx.mixes.video.get("result_pool", 5)))
    if not site.host.endswith("youtube.com"):
        raise PageError(f"no player implemented for {site.host}")
    ctx.play_youtube(term, result_index)
    ctx.watch_media()
    return ctx.visited
