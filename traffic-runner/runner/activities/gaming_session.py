"""gaming_session: open launcher/store pages, then hold a long low-bitrate bidirectional
session (catalog §2). Approximation (decided 23.10, catalog §6): store pages of the gaming
mix for 2-5 min, then the game page of the peer VM, a browser game over a WebSocket that
sends small inputs and receives small game states 20-60 times per second in both
directions. `voice: true` is a separate voice_call row of the scheduler.
"""

from .. import peer as peer_client

ID = "gaming_session"
IMPLEMENTED = True
ROLES = ("laptop",)
DEFAULT_DURATION = (3600, 7200)
NEEDS_MIX = True
DEFAULT_MIX = "gaming"
MIX_KIND = None
NEEDS_BROWSER = True

STORE = (120, 300)
STORE_DWELL = (30, 90)
TICK = (20, 60)
RETRY_PAUSE = 5.0


def run(ctx, rng, duration, mix):
    peer = peer_client.from_env()  # not_implemented if the VM is not configured
    store_end = min(rng.uniform(*STORE), 0.25 * duration)  # at most a quarter of the block
    tick = rng.randint(*TICK)
    game_seed = rng.randint(1, 2**31 - 1)
    while ctx.remaining() > 0 and ctx.elapsed() < store_end:
        url = mix.pick(rng, ctx.hung_sites).resolve_url(rng)
        dwell = rng.uniform(*STORE_DWELL)
        scroll_seed = rng.random()
        if ctx.open(url):
            ctx.dwell(min(dwell, store_end - ctx.elapsed()), scroll_seed)
        else:
            ctx.idle(RETRY_PAUSE)
    ctx.play_game(peer.game_url(tick, game_seed))
    ctx.watch_media(check_every=30.0)
    return ctx.visited
