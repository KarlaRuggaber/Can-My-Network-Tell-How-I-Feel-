"""study_block: like work_block with the study mix (LMS, documents, scholarly search) plus
PDF downloads of 1-5 MB (catalog §2). See _desk.py.

Runner choices: 1-3 PDFs per hour, taken from mixes.yaml `documents.pdfs`. Each download
opens the paper's page first and then fetches the PDF from it, so the browser loads the
file completely through its normal network path.
"""

from ._desk import run_desk

ID = "study_block"
IMPLEMENTED = True
ROLES = ("laptop",)
DEFAULT_DURATION = (2700, 7200)
NEEDS_MIX = True
DEFAULT_MIX = "study"
MIX_KIND = None
NEEDS_BROWSER = True

REFRESH = (120, 300)
PAGES_PER_HOUR = (2, 5)
PAGE_DWELL = (60, 300)
PDFS_PER_HOUR = (1, 3)


def run(ctx, rng, duration, mix):
    pdfs = ctx.mixes.documents.get("pdfs") or []
    return run_desk(ctx, rng, duration, mix, REFRESH, PAGES_PER_HOUR, PAGE_DWELL, PDFS_PER_HOUR, pdfs)
