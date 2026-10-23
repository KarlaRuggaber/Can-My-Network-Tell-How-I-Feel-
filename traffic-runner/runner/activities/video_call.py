"""video_call: WebRTC call with fake camera and microphone against a counterpart outside
the home network (catalog §2). See _call.py.

Every `platform` (jitsi, zoom, teams) runs on the self-hosted Jitsi of the peer VM: zoom
and teams would need accounts. The host is therefore the VM's, which, like jit.si and
zoom.us, is in no thesis list; only teams.microsoft.com would count as PRODUCTIVITY.
"""

from ._call import run_call

ID = "video_call"
IMPLEMENTED = True
ROLES = ("phone", "laptop")
DEFAULT_DURATION = None  # "as block"
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True
BROWSER_MODE = "call"


def run(ctx, rng, duration, mix):
    return run_call(ctx, duration, video=True)
