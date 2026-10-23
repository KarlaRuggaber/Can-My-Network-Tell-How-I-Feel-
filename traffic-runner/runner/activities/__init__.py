"""Activity registry. See base.py for the module interface."""

from . import (
    browse,
    crisis_resource_visit,
    idle_connected,
    messaging,
    music_background,
    phone_check,
    repeat_visit_loop,
    sh_adjacent_lookup,
    social_passive,
    social_post,
    study_block,
    video_call,
    video_stream,
    voice_call,
    work_block,
)

ACTIVITIES = {m.ID: m for m in (
    phone_check, browse, repeat_visit_loop, video_stream, music_background, idle_connected,
    social_passive, work_block, study_block, crisis_resource_visit, sh_adjacent_lookup,
    messaging, social_post, video_call, voice_call,
)}

# Catalog §2 IDs without a module yet. Running them logs status not_implemented, so a
# scheduler can already use the full catalog.
CATALOG_ONLY = ("gaming_session", "away")
