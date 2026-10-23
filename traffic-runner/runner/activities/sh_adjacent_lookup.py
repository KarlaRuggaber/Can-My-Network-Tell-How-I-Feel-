"""sh_adjacent_lookup: DNS lookups only, of placeholder names sh-adjacent-NN.invalid, no
connection (catalog §2). Placeholder for self-harm-adjacent content: no real harmful domain
is ever contacted or written down. The names land in the gateway's DNS log and feed; the
`.invalid` top-level domain never resolves. The log's `domains` lists the queried names.
"""

ID = "sh_adjacent_lookup"
IMPLEMENTED = True
ROLES = ("phone",)
DEFAULT_DURATION = (5, 30)  # "seconds"
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = False

LOOKUPS = (1, 3)
GAP = (1.0, 5.0)
NAME_RANGE = (1, 20)


def run(ctx, rng, duration, mix):
    lo, hi = ctx.range("lookups", LOOKUPS)
    for _ in range(rng.randint(int(lo), int(hi))):
        name = f"sh-adjacent-{rng.randint(*NAME_RANGE):02d}.invalid"
        gap = rng.uniform(*GAP)
        if ctx.remaining() <= 0:
            break
        ctx.dns_lookup(name)
        ctx.sleep_without_browser(gap)
    return ctx.visited
