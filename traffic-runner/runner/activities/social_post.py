"""social_post: log into a test account and upload a photo or story (catalog §2).

Stub: needs a social test account. Logs status not_implemented until that exists.
"""

from .base import not_implemented

ID = "social_post"
IMPLEMENTED = False
ROLES = ("phone",)
DEFAULT_DURATION = (120, 300)
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True

run = not_implemented(ID, "needs a social test account")
