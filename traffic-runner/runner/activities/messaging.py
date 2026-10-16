"""messaging: send 3-10 messages via a web client, reply to a scripted counterpart (catalog §2).

Stub: needs test accounts and a scripted counterpart account. Logs status not_implemented until that exists.
"""

from .base import not_implemented

ID = "messaging"
IMPLEMENTED = False
ROLES = ("phone",)
DEFAULT_DURATION = (120, 600)
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True

run = not_implemented(ID, "needs test accounts and a scripted counterpart account")
