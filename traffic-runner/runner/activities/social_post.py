"""social_post: log into a test account and upload 1 photo (1-3 MB) (catalog §2).

Platform (decided 23.10): Reddit, shared account u/CMNTHIF, posting ONLY into the private
subreddit r/CMNTHIF (config/accounts.yaml). The image is generated (random pixels, so the
upload has the requested size and is obviously not a photo). Before clicking "Post" the
driver checks that the page is the submit page of exactly that subreddit, and afterwards
that the new post lives there; anything else is an error, never a post elsewhere.
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
SESSION_PLATFORM = "reddit"

IMAGE_MB = (1.0, 3.0)
VIEW = (20, 60)
TITLES = ["Test upload", "Testbild", "Test post (automated)", "Upload test", "Bildtest"]


def run(ctx, rng, duration, mix):
    subreddit = ctx.accounts["reddit"]["subreddit"]
    size = int(rng.uniform(*IMAGE_MB) * 1_000_000)
    image_seed = rng.random()
    title = f"{rng.choice(TITLES)} {rng.randint(1000, 9999)}"
    view, view_seed = rng.uniform(*VIEW), rng.random()
    with tempfile.TemporaryDirectory() as tmp:
        image = make_png(Path(tmp) / "test.png", size, image_seed)
        if not ctx.reddit_post(subreddit, title, image):
            raise PageError("post was not created")
    ctx.dwell(view, view_seed)  # look at the new post
    return ctx.visited
