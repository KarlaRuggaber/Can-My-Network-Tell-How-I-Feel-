"""phone_check: open 1-3 pages from the mix, dwell 20-90 s each, scroll (catalog §2).

Default duration 1-5 min. The run ends when its pages are done or the duration is over,
whichever comes first; the log records the real end time. Profiles can override the page
count and dwell with --pages / --dwell (catalog §1).
"""

ID = "phone_check"
IMPLEMENTED = True
ROLES = ("phone",)
DEFAULT_DURATION = (60, 300)
NEEDS_MIX = True
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True

PAGES = (1, 3)
DWELL = (20, 90)


def run(ctx, rng, duration, mix):
    pages_lo, pages_hi = ctx.range("pages", PAGES)
    dwell_lo, dwell_hi = ctx.range("dwell", DWELL)
    for _ in range(rng.randint(int(pages_lo), int(pages_hi))):
        url = mix.pick(rng).resolve_url(rng)
        dwell = rng.uniform(dwell_lo, dwell_hi)
        scroll_seed = rng.random()
        if ctx.remaining() <= 0:
            break
        if ctx.open(url):
            ctx.dwell(dwell, scroll_seed)
    return ctx.visited
