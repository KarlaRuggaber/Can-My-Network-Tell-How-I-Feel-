"""crisis_resource_visit: open 1-3 pages of help-seeking resources, dwell 1-4 min each
(catalog §2). Only in profiles with the suicidality overlay. Ends when its pages are done;
the duration (2-10 min) is an upper bound.
"""

ID = "crisis_resource_visit"
IMPLEMENTED = True
ROLES = ("phone",)
DEFAULT_DURATION = (120, 600)
NEEDS_MIX = True
DEFAULT_MIX = "crisis_help"
MIX_KIND = None
NEEDS_BROWSER = True

PAGES = (1, 3)
DWELL = (60, 240)


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
