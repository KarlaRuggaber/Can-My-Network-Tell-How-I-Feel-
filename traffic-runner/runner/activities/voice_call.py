"""voice_call: WebRTC audio-only call against the counterpart outside the home network
(catalog §2), also the voice chat of a gaming_session with voice. See _call.py and
video_call.py (platforms).
"""

from ._call import run_call

ID = "voice_call"
IMPLEMENTED = True
ROLES = ("phone", "laptop")
DEFAULT_DURATION = None  # "as block"
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True
BROWSER_MODE = "call"


def run(ctx, rng, duration, mix):
    return run_call(ctx, rng, duration, video=False)
