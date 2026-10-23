"""repeat_visit_loop: revisit the same 2-3 pages every 1-3 min with a fresh DNS lookup
each time (catalog §2, rumination dial).

Each revisit opens a new browser context. Chromium keeps a separate DNS cache per context,
so every visit does a fresh DNS query (checked in the net-log: 3 contexts, 3 lookups; 2
visits in one context, 1 lookup). The browser process itself keeps running, which avoids
its start-up requests (accounts.google.com) on every revisit.
"""

ID = "repeat_visit_loop"
IMPLEMENTED = True
ROLES = ("phone",)
DEFAULT_DURATION = (600, 1800)
NEEDS_MIX = True
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True

PAGES = (2, 3)
INTERVAL = (60, 180)


def run(ctx, rng, duration, mix):
    pages_lo, pages_hi = ctx.range("pages", PAGES)
    wanted = rng.randint(int(pages_lo), int(pages_hi))
    sites = []
    for _ in range(20 * wanted):  # distinct sites, as far as the mix allows
        if len(sites) == wanted:
            break
        site = mix.pick(rng)
        if site not in sites:
            sites.append(site)
    urls = [s.resolve_url(rng) for s in sites]

    while ctx.remaining() > 0:
        url = rng.choice(urls)
        interval = rng.uniform(*INTERVAL)
        visit_start = ctx.elapsed()
        ctx.fresh_context()
        ctx.open(url)
        ctx.idle(interval - (ctx.elapsed() - visit_start))
    return ctx.visited
