"""phone_check: open pages from the mix one after another, dwell 20-90 s each, scroll
(catalog §2).

Without --pages the device keeps opening pages until the duration is used up (default
duration 1-5 min). With --pages (a profile's `pages`) it opens exactly that many and ends,
possibly before the duration is over; the log records the real end time.
"""

ID = "phone_check"
IMPLEMENTED = True
ROLES = ("phone",)
DEFAULT_DURATION = (60, 300)
NEEDS_MIX = True
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True

DWELL = (20, 90)
RETRY_PAUSE = 5.0  # after a page failed to load


def run(ctx, rng, duration, mix):
    dwell_lo, dwell_hi = ctx.range("dwell", DWELL)
    pages = ctx.overrides.get("pages")
    limit = rng.randint(int(pages[0]), int(pages[1])) if pages else None
    opened = 0
    while ctx.remaining() > 0 and (limit is None or opened < limit):
        url = mix.pick(rng).resolve_url(rng)
        dwell = rng.uniform(dwell_lo, dwell_hi)
        scroll_seed = rng.random()
        opened += 1
        if ctx.open(url):
            ctx.dwell(dwell, scroll_seed)
        else:
            ctx.idle(RETRY_PAUSE)
    return ctx.visited
