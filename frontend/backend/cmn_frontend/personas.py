"""Persona metadata and the expected thesis output from each profile's section 9.

Source: profiles/tier2-clinical/*.md, table "Expected thesis output" (calibrated gateway config).
"present" values: "present", "no", "elevated" (moves but stays below the gate),
"borderline", "flag" (outside the gate, C9).
"""

from __future__ import annotations

from typing import Any

PERSONAS: dict[str, dict[str, Any]] = {
    "gw_insomnia_a": {
        "name": "Ben",
        "condition": "Insomnia (moderate)",
        "profile": "profiles/tier2-clinical/insomnia-moderate.md",
        "baseline_profile": "9to5-worker",
        "summary": "Later sleep onset and 2-4 phone bursts between 01:00 and 04:00 on 3-5 nights a week; "
                   "the signal lands on the day after a symptomatic night.",
        "expected": {
            "C1": {"present": "elevated", "note": "F8 night/day ratio rises, but weight 0.35 cannot reach θ alone"},
            "C2": {"present": "no", "note": "≈ baseline; a rise would mean the profile leaks into depression"},
            "C3": {"present": "no", "note": "not scripted"},
            "C4": {"present": "present", "note": "↑ on the 8 ± 2 days after symptomatic nights"},
            "C5": {"present": "no", "note": "not scripted"},
            "C6": {"present": "no", "note": "weekdays unchanged; later wake only on weekends"},
            "C7": {"present": "no", "note": "not scripted"},
            "C8": {"present": "no", "note": "≈ baseline"},
            "C9": {"present": "no", "note": "not scripted"},
        },
        "episode": {"expected": "no", "note": "1 criterion present; insomnia is not depression"},
    },
    "gw_mdd_suicidality_a": {
        "name": "Maria",
        "condition": "Major depressive disorder (severe) with suicidality overlay",
        "profile": "profiles/tier2-clinical/mdd-severe-suicidality.md",
        "baseline_profile": "student",
        "summary": "Activity collapse, social withdrawal, later and more variable sleep, early waking, "
                   "rumination loops; 2-4 night-time episodes with crisis-resource visits.",
        "expected": {
            "C1": {"present": "present", "note": "F8 ↑↑, F7 ↓, F1 ↓, F4 ↑"},
            "C2": {"present": "present", "note": "core: C2_F1, F3, F4, F6 all ↓ (inverted → μ ↑)"},
            "C3": {"present": "no", "note": "mild, not scripted"},
            "C4": {"present": "present", "note": "later onset, micro-sessions, night/day bytes ↑"},
            "C5": {"present": "no", "note": "not observable"},
            "C6": {"present": "borderline", "note": "↑ on ~6-8 days; early-waking days lower C6_F8"},
            "C7": {"present": "no", "note": "not observable"},
            "C8": {"present": "present", "note": "DNS bursts ↑, repeated queries ↑ (if bands sit above baseline)"},
            "C9": {"present": "flag", "note": "crisis-line hits on 2-4 days, outside the gate"},
        },
        "episode": {"expected": "borderline",
                    "note": "C1, C2, C4, C8 present; a 5th criterion can only come from C6"},
    },
    "gw_social_anxiety_a": {
        "name": "Carl",
        "condition": "Social anxiety disorder (moderate)",
        "profile": "profiles/tier2-clinical/social-anxiety-moderate.md",
        "baseline_profile": "student",
        "summary": "Fewer calls without camera/mic, no voice chat, going-out evenings replaced by "
                   "solitary home sessions; passive and asynchronous use kept or increased.",
        "expected": {
            "C1": {"present": "elevated", "note": "F4 down/up ratio ↑, F8 slightly ↑"},
            "C2": {"present": "elevated", "note": "only C2_F4 upstream rate moves (0.25 of the weight)"},
            "C3": {"present": "no", "note": "not scripted"},
            "C4": {"present": "no", "note": "≈ baseline"},
            "C5": {"present": "no", "note": "not scripted"},
            "C6": {"present": "no", "note": "≈ baseline"},
            "C7": {"present": "no", "note": "not scripted"},
            "C8": {"present": "no", "note": "≈ baseline"},
            "C9": {"present": "no", "note": "not scripted"},
        },
        "episode": {"expected": "no", "note": "partial C1/C2 elevation, no criterion present"},
    },
}

PHASE_LABEL = {"warmup": "warm-up", "baseline": "baseline", "profile": "current"}  # current = clinical phase


def persona_meta(dataset: str) -> dict[str, Any]:
    meta = PERSONAS.get(dataset)
    if meta is None:
        return {"name": dataset, "condition": "", "profile": None, "baseline_profile": None,
                "summary": "", "expected": {}, "episode": None}
    return meta
