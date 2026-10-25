"""social_post: upload 1 photo (1-3 MB) to a social platform (catalog §2).

Platform (decided 25.10, replaces Reddit): Discord, through a webhook of one channel in the
project's private server (runner/discord.py, config/accounts.yaml). Reddit flagged the shared
account as automated and requires app registration plus API approval; Discord webhooks are
made for automated posts. discord.com is in the thesis SOCIAL list, so the upload counts for
the same social-upload metrics as before.

The image is generated (random pixels, so the upload has the requested size and is obviously
not a photo). The webhook must be the configured one, and Discord's reply must name the
configured channel; anything else is an error, never a post elsewhere. Afterwards the browser
opens the uploaded image, like looking at the new post.
"""

import tempfile
from pathlib import Path

from ..context import PageError
from ..testimage import make_png

ID = "social_post"
IMPLEMENTED = True
ROLES = ("phone",)
DEFAULT_DURATION = (120, 300)
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True
WEBHOOK_PLATFORM = "discord"  # the CLI loads the webhook (not_implemented if not set up)

IMAGE_MB = (1.0, 3.0)
VIEW = (20, 60)
TITLES = ["Test upload", "Testbild", "Test post (automated)", "Upload test", "Bildtest"]


def run(ctx, rng, duration, mix):
    size = int(rng.uniform(*IMAGE_MB) * 1_000_000)
    image_seed = rng.random()
    title = f"{rng.choice(TITLES)} {rng.randint(1000, 9999)}"
    view, view_seed = rng.uniform(*VIEW), rng.random()
    with tempfile.TemporaryDirectory() as tmp:
        image = make_png(Path(tmp) / "test.png", size, image_seed)
        msg = ctx.webhook_post(image, title)
        if not msg:
            raise PageError("post was not created")
    ctx.open(msg["attachments"][0]["url"])  # look at the new post
    ctx.dwell(view, view_seed)
    return ctx.visited
