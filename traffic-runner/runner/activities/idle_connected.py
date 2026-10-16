"""idle_connected: device stays on the network and does nothing (catalog §2).

No browser is started. Note: a container has no OS background traffic, unlike a real
phone or laptop, so this block is completely silent on the wire.
"""

ID = "idle_connected"
IMPLEMENTED = True
ROLES = ("phone", "laptop")
DEFAULT_DURATION = None  # "as block"
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = False


def run(ctx, rng, duration, mix):
    ctx.sleep_without_browser(duration)
    return []
