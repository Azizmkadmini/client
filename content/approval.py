"""Workflow approbation contenu."""

from __future__ import annotations

from content.store import ContentStore


def submit_for_review(draft_id: str, reviewer_note: str = "") -> dict:
    store = ContentStore()
    d = store.update_draft(draft_id, status="review")
    if reviewer_note:
        title = (d.get("title") or "Review") + f" — {reviewer_note[:80]}"
        return store.update_draft(draft_id, title=title)
    return d


def approve_draft(draft_id: str) -> dict:
    store = ContentStore()
    return store.update_draft(draft_id, status="approved")


def reject_draft(draft_id: str, reason: str = "") -> dict:
    store = ContentStore()
    d = store.update_draft(draft_id, status="rejected")
    if reason:
        store.update_draft(draft_id, title=(d.get("title") or "") + f" [rejet: {reason}]")
    return store.get_draft(draft_id)
