"""Common interface of all activity modules (one module per activity ID of catalog §2).

Every module defines:

    ID                str      activity ID from the catalog
    IMPLEMENTED       bool     False = stub, logs status not_implemented
    ROLES             tuple    device roles the catalog intends (only a warning if violated)
    DEFAULT_DURATION  (lo, hi) seconds, drawn with the RNG if --duration is omitted;
                      None = "as block": --duration is required
    NEEDS_MIX         bool     whether the activity picks sites from --mix
    DEFAULT_MIX       str|None mix used when --mix is omitted
    MIX_KIND          str|None only sites of this kind ("video") are eligible
    NEEDS_BROWSER     bool     False = runs without a browser (idle_connected)

    def run(ctx: RunContext, rng: random.Random, duration: float, mix: Mix | None) -> list[str]
        Returns the hosts of the main documents actually loaded.

Reproducibility rule: draw everything an iteration needs from `rng` *before* touching the
network. Values that depend on page content (which link to follow, how to scroll) get
their own sub-RNG seeded from one `rng.random()` draw, so a slow or failing page never
shifts the rest of the sequence.
"""

from __future__ import annotations

from ..context import NotImplementedActivity


def not_implemented(activity_id: str, reason: str):
    """Build the run() of a stub activity."""

    def run(ctx, rng, duration, mix):
        raise NotImplementedActivity(f"{activity_id}: {reason}")

    return run
