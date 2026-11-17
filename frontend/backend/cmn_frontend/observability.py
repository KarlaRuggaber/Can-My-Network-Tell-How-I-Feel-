"""What the network can tell per DSM-5 criterion, from profiles/symptom-network-mapping.md (§3, §8)
and profiles/thesis-alignment.md (known issues B3, B5, B8, B9).

Levels: "good" (clear, fairly specific signal), "partial" (present but ambiguous or needs a baseline),
"none" (no reliable network trace). Shown to clinicians and parents, used when choosing a patient's
focus, and given to the assistant so explanations stay honest about what the data can carry.
"""

from __future__ import annotations

from typing import Any

OBSERVABILITY: dict[str, dict[str, Any]] = {
    "C1": {"level": "partial", "observes": "flatter daily curve, less overall use, fewer social sites, more use at night",
           "cannot": "mood itself; sleep and social metrics are mixed into this criterion",
           "caveats": ["The thesis's hourly-variation metric is scored in the reversed direction (B9).",
                       "Insomnia and social anxiety also raise C1 (misattribution, B6)."]},
    "C2": {"level": "partial", "observes": "fewer different sites, fewer chat sessions, less upload, less use of work and study tools",
           "cannot": "which hobby stopped; a gaming drop shows only indirectly",
           "caveats": ["Good with a well-established personal baseline; introversion lowers the same metrics."]},
    "C3": {"level": "none", "observes": "food-delivery and diet-site visits only",
           "cannot": "appetite or weight; the site signal goes either way and is too ambiguous",
           "caveats": ["Not scored in the thesis configuration."]},
    "C4": {"level": "good", "observes": "quiet window at night, use at night, night-to-night variation, early-morning bursts",
           "cannot": "asleep vs. away vs. device off; sleep on mobile data or without devices",
           "caveats": ["The thesis's wake-time metric produces a midnight artifact (B3).",
                       "Early waking is scored as late waking (B5)."]},
    "C5": {"level": "none", "observes": "only unvalidated proxies (network re-associations, very short sessions)",
           "cannot": "physical agitation or slowing", "caveats": ["Not scored in the thesis configuration."]},
    "C6": {"level": "partial", "observes": "fewer and shorter sessions, later first activity, long idle stretches",
           "cannot": "tiredness itself; travel or a quiet day look the same",
           "caveats": ["Not scored in the thesis configuration yet."]},
    "C7": {"level": "none", "observes": "visits to mental-health and help sites (hostnames only)",
           "cannot": "feelings of worthlessness or guilt; content and search terms are encrypted",
           "caveats": ["Help-line visits can land here as well as in C9."]},
    "C8": {"level": "partial", "observes": "rapid switching between sites, repeated look-ups, short pauses between actions",
           "cannot": "concentration itself; multitasking at work or school looks similar",
           "caveats": ["Rated good for switching patterns in the mapping; confounded by work and study."]},
    "C9": {"level": "partial", "observes": "visits to crisis-line and help sites (hostnames via DNS), often at night",
           "cannot": "thoughts or intent; search terms and page content (no URLs in the gateway data)",
           "caveats": ["Episodic: shown as a flag, not through the N-of-M gate (B8).",
                       "DNS-over-HTTPS or iCloud Private Relay hide the hostnames.",
                       "'Self-harm forum visits' counts all reddit.com packets without URLs and is not used."]},
}

# Which criteria each observed risk speaks to (for choosing a patient's focus by criterion).
RISK_CRITERIA: dict[str, list[str]] = {
    "later_nights": ["C4"], "later_mornings": ["C4", "C6"], "shorter_quiet": ["C4"],
    "night_use": ["C4", "C1"], "more_use": ["C1"], "less_use": ["C6", "C1"],
    "fewer_chats": ["C2", "C1"], "fewer_sites": ["C2"], "sensitive_sites": ["C9"],
}


def table(configured: list[str]) -> dict[str, dict[str, Any]]:
    return {c: {**v, "scored": c in configured} for c, v in OBSERVABILITY.items()}
