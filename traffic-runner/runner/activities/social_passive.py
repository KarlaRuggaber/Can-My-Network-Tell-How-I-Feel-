"""social_passive: scroll a feed (load more content every 5-15 s), open 0-2 videos
(catalog §2). Runs for the whole block.

Runner choices the catalog leaves open:
- Long blocks switch to another site of the mix every 3-10 min, so a 2-hour block does not
  stay on one feed (profiles use mixes like social_passive + streaming + news).
- A feed whose page hangs (e.g. stuck in a bot check) is left after the step limit; the browser
  is restarted and the block continues on another site of the mix (runner/steps.py, 26.10).
- "Open a video" follows one internal link of the feed (a post or video page), watches it
  for 30-120 s and goes back to the feed. Without login the runner cannot tell video posts
  from other posts, so it is an approximation.
"""

ID = "social_passive"
IMPLEMENTED = True
ROLES = ("phone", "laptop")
DEFAULT_DURATION = None  # "as block"
NEEDS_MIX = True
DEFAULT_MIX = "social_passive"
MIX_KIND = None
NEEDS_BROWSER = True

VIDEOS = (0, 2)
VIDEO_WATCH = (30, 120)
SEGMENT = (180, 600)
RETRY_PAUSE = 5.0


def run(ctx, rng, duration, mix):
    # Videos are planned up front: when (share of the block), how long, which link.
    videos = sorted((rng.uniform(0.1, 0.9) * duration, rng.uniform(*VIDEO_WATCH), rng.random())
                    for _ in range(rng.randint(*VIDEOS)))
    while ctx.remaining() > 0:
        url = mix.pick(rng, ctx.hung_sites).resolve_url(rng)
        segment_end = ctx.elapsed() + rng.uniform(*SEGMENT)
        feed_seed = rng.random()
        if not ctx.open(url):
            ctx.idle(RETRY_PAUSE)
            continue
        chunk = 0
        while ctx.remaining() > 0 and ctx.elapsed() < segment_end:
            next_video = videos[0][0] if videos else float("inf")
            if ctx.elapsed() >= next_video:
                _, watch, link_seed = videos.pop(0)
                if ctx.follow_link(link_seed):
                    ctx.dwell(watch, f"{link_seed}/watch")
                    if ctx.take_hung():
                        break
                    ctx.open(url)  # back to the feed
                if ctx.take_hung():
                    break
                continue
            ctx.scroll_feed(min(segment_end, next_video) - ctx.elapsed(), f"{feed_seed}/{chunk}")
            chunk += 1
            if ctx.take_hung():  # the page hung, the browser was restarted: next site of the mix
                break
    return ctx.visited
