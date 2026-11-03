from math import ceil


TRANSITIONS = {
    "AWAITING_PAYMENT": {"PAID", "PAYMENT_FAILED", "EXPIRED", "CANCELLED"},
    "PAYMENT_FAILED": {"PAID", "AWAITING_PAYMENT", "EXPIRED"},
    "PAID": {"QUEUED", "PAUSED", "REFUND_PENDING"},
    "QUEUED": {"PRINTING", "PAUSED", "COMPLETION_UNCERTAIN"},
    "PRINTING": {"COMPLETED", "COMPLETION_UNCERTAIN", "FAILED"},
    "PAUSED": {"PAID", "REFUND_PENDING"},
    "COMPLETION_UNCERTAIN": {"REFUND_PENDING"},
    "FAILED": {"REFUND_PENDING"},
    "REFUND_PENDING": {"REFUNDED"},
}


def transition(job, target):
    if target not in TRANSITIONS.get(job.status, set()):
        raise ValueError(f"Invalid transition {job.status} -> {target}")
    job.status = target


def select_pages(selection, page_count):
    if not selection:
        return list(range(1, page_count + 1))
    pages = set()
    for part in selection.split(","):
        bounds = part.strip().split("-")
        if len(bounds) not in (1, 2) or not all(x.isdigit() for x in bounds):
            raise ValueError("Use page ranges such as 1-3,5")
        start, end = int(bounds[0]), int(bounds[-1])
        if start < 1 or end > page_count or start > end:
            raise ValueError("Page selection is outside the document")
        pages.update(range(start, end + 1))
    return sorted(pages)


def price(pages, copies, duplex, tiers):
    sides = len(pages) * copies
    tier = next((t for t in tiers if t.min_sides <= sides and (t.max_sides is None or sides <= t.max_sides)), None)
    if tier is None:
        raise ValueError("No pricing tier covers this order")
    return dict(printed_sides=sides, sheets=(ceil(len(pages) / 2) if duplex else len(pages)) * copies,
                rate_ugx=tier.rate_ugx, total_ugx=sides * tier.rate_ugx, pricing_version=tier.version)
