"""work_block: home page reloaded every 2-5 min, 2-5 other work pages per hour (catalog §2).
See _desk.py. Login-free approximation: the work mix has public pages of PRODUCTIVITY
domains (github, gitlab, trello, asana, todoist); web mail, calendar and editing a document
need test accounts.
"""

from ._desk import run_desk

ID = "work_block"
IMPLEMENTED = True
ROLES = ("laptop",)
DEFAULT_DURATION = (3600, 7200)
NEEDS_MIX = True
DEFAULT_MIX = "work"
MIX_KIND = None
NEEDS_BROWSER = True

REFRESH = (120, 300)
PAGES_PER_HOUR = (2, 5)
PAGE_DWELL = (60, 300)


def run(ctx, rng, duration, mix):
    return run_desk(ctx, rng, duration, mix, REFRESH, PAGES_PER_HOUR, PAGE_DWELL)
