"""Shared engine of work_block and study_block (catalog §2): keep one "home" page open
(mailbox, LMS) and reload it every 2-5 min; in between open 2-5 other pages per hour from
the mix and, for study_block, download PDFs. Without login the home page is a public page
of the mix (e.g. a GitHub or Scholar page); writing in a document is not possible.
"""


def run_desk(ctx, rng, duration, mix, refresh, pages_per_hour, page_dwell, pdfs_per_hour=None, pdfs=()):
    home = mix.pick(rng, ctx.hung_sites).resolve_url(rng)
    page_rate = rng.uniform(*pages_per_hour) / 3600
    pdf_rate = rng.uniform(*pdfs_per_hour) / 3600 if pdfs and pdfs_per_hour else 0.0
    ctx.open(home)
    while ctx.remaining() > 0:
        # Everything this interval needs is drawn before any network access.
        interval = rng.uniform(*refresh)
        open_page = rng.random() < page_rate * interval
        page_url = mix.pick(rng, ctx.hung_sites).resolve_url(rng)
        page_seconds = rng.uniform(*page_dwell)
        page_seed = rng.random()
        get_pdf = rng.random() < pdf_rate * interval
        pdf = rng.choice(pdfs) if pdfs else None
        read_seed = rng.random()

        start = ctx.elapsed()
        if open_page and ctx.open(page_url):
            ctx.dwell(min(page_seconds, 0.8 * interval), page_seed)
        if get_pdf:
            ctx.download(pdf["page"], pdf["pdf"])
        ctx.dwell(interval - (ctx.elapsed() - start), read_seed)
        if ctx.remaining() <= 0:
            break
        ctx.open(home)  # refresh the mailbox / LMS
    return ctx.visited
