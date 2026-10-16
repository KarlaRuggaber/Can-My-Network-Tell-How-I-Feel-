"""video_call: WebRTC call with fake camera and mic against a counterpart outside the network (catalog §2).

Stub: needs a call counterpart outside the home network (and accounts for zoom/teams). Logs status not_implemented until that exists.
"""

from .base import not_implemented

ID = "video_call"
IMPLEMENTED = False
ROLES = ("phone", "laptop")
DEFAULT_DURATION = None  # "as block"
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True

run = not_implemented(ID, "needs a call counterpart outside the home network (and accounts for zoom/teams)")
