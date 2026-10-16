"""voice_call: WebRTC audio-only call against a counterpart outside the network (catalog §2).

Stub: needs a call counterpart outside the home network (and accounts for discord/teams). Logs status not_implemented until that exists.
"""

from .base import not_implemented

ID = "voice_call"
IMPLEMENTED = False
ROLES = ("phone", "laptop")
DEFAULT_DURATION = None  # "as block"
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True

run = not_implemented(ID, "needs a call counterpart outside the home network (and accounts for discord/teams)")
