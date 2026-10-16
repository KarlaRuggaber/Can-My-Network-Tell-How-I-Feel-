"""music_background: play an audio livestream in the background (catalog §2).

The catalog has no login-free audio source yet; mixes.yaml `audio.streams` proposes the
SRF 3 MP3 livestream. Runs for the whole block, usually in parallel to another block on
another device.
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
    ctx.play_audio(stream["url"])
    ctx.watch_media(check_every=30.0)
    return ctx.visited
