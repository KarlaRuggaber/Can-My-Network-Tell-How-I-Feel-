"""Facts from profiles/activity-catalog.md (§2 activities, §3 mix categories) the scheduler needs.

Keep in sync with the catalog. The runner has its own copy in traffic-runner/runner/activities/.
"""

from __future__ import annotations

PHONE, LAPTOP, ANY = "phone", "laptop", "any"
ROLES = (PHONE, LAPTOP)

# activity id -> (device role, default duration in seconds or None = "as block", default mix key)
ACTIVITIES: dict[str, tuple[str, tuple[int, int] | None, str | None]] = {
    "phone_check":           (PHONE,  (60, 300),    None),
    "browse":                (ANY,    None,         None),
    "social_passive":        (ANY,    None,         "social_passive"),   # phone, laptop possible
    "social_post":           (PHONE,  (120, 300),   "social_post"),
    "messaging":             (PHONE,  (120, 600),   "messaging"),
    "video_call":            (ANY,    None,         "call"),
    "voice_call":            (ANY,    None,         "call"),
    "video_stream":          (ANY,    (1800, 7200), "streaming"),
    "music_background":      (LAPTOP, None,         "audio"),
    "work_block":            (LAPTOP, (3600, 7200), "work"),
    "study_block":           (LAPTOP, (2700, 7200), "study"),
    "gaming_session":        (LAPTOP, (3600, 7200), "gaming"),
    "repeat_visit_loop":     (PHONE,  (600, 1800),  None),
    "crisis_resource_visit": (PHONE,  (120, 600),   "crisis_help"),
    "sh_adjacent_lookup":    (PHONE,  (10, 30),     None),   # "seconds"; DNS only
    "idle_connected":        (ANY,    None,         None),
    "away":                  (ANY,    None,         None),
}

# Activities that pick sites from --mix in the runner and have no default: the profile must give `mix`.
NEEDS_MIX = {"phone_check", "browse", "repeat_visit_loop"}

# Mix keys of catalog §3. `call` and `audio` are pseudo-keys: the runner takes no --mix for them.
MIX_KEYS = {"messaging", "social_passive", "social_post", "streaming", "news", "work", "study",
            "search", "shopping", "gaming", "crisis_help", "call", "audio"}
NO_RUNNER_MIX = {"call", "audio"}

CALLS = {"video_call", "voice_call"}
# Long sequences of page visits that resume after an interruption: split around calls instead of pushed.
SPLITTABLE = {"work_block", "study_block"}
# Background companions (`with:`): run in parallel on the same device and are allowed during calls.
COMPANIONS = {"music_background"}

CALL_PLATFORMS = {"zoom", "teams", "jitsi", "discord"}
GAMING_VOICE_PLATFORM = "discord"


def role_ok(activity: str, role: str) -> bool:
    want = ACTIVITIES[activity][0]
    return want == ANY or want == role


def default_mix(activity: str) -> str | None:
    return ACTIVITIES[activity][2]


def default_duration(activity: str) -> tuple[int, int] | None:
    return ACTIVITIES[activity][1]
