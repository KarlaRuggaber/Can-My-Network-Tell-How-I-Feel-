"""music_background: play an audio livestream in the background (catalog §2).

Sources come from mixes.yaml `audio.streams`, chosen with the RNG:
  kind: page    an SRF radio live page (srf.ch = STREAMING list), lowest quality level
  kind: stream  a direct stream URL played in an empty page (e.g. the SRG MP3 stream)
Runs for the whole block, usually in parallel to another block on another device.
"""

from ..context import NotImplementedActivity

ID = "music_background"
IMPLEMENTED = True
ROLES = ("laptop",)
DEFAULT_DURATION = None  # "as block"
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True


def run(ctx, rng, duration, mix):
    streams = ctx.mixes.audio.get("streams") or []
    if not streams:
        raise NotImplementedActivity("no audio stream configured in mixes.yaml")
    stream = rng.choice(streams)
    if stream.get("kind", "stream") == "page":
        ctx.play_audio_page(stream["url"])
    else:
        ctx.play_audio(stream["url"])
    ctx.watch_media(check_every=30.0)
    return ctx.visited
