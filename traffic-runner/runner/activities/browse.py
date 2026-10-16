"""browse: visit pages from the mix, dwell 30-180 s, scroll, follow 1-2 internal links
per page (catalog §2). Runs for the whole block.
"""

ID = "browse"
IMPLEMENTED = True
ROLES = ("phone", "laptop")
DEFAULT_DURATION = None  # "as block"
NEEDS_MIX = True
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True

DWELL = (30, 180)
LINKS = (1, 2)
RETRY_PAUSE = 5.0  # after a page failed to load


def run(ctx, rng, duration, mix):
    dwell_lo, dwell_hi = ctx.range("dwell", DWELL)
    while ctx.remaining() > 0:
        url = mix.pick(rng).resolve_url(rng)
        dwell = rng.uniform(dwell_lo, dwell_hi)
        scroll_seed = rng.random()
        links = [(rng.random(), rng.uniform(dwell_lo, dwell_hi), rng.random())
                 for _ in range(rng.randint(*LINKS))]

        if not ctx.open(url):
            ctx.idle(RETRY_PAUSE)
            continue
        ctx.dwell(dwell, scroll_seed)
        for link_seed, link_dwell, link_scroll_seed in links:
            if ctx.remaining() <= 0:
                break
            if ctx.follow_link(link_seed):
                ctx.dwell(link_dwell, link_scroll_seed)
    return ctx.visited
