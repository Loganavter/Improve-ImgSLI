"""Shared test helper: put a GalleryItem in the ACTIVE analysis phase.

The placeholder dot set (the full requested axis set, neutral) is an
"analysis in progress" affordance since 2026-10-22 — it must not outlive the
analysis (owner: the 8 dots stayed after "Analyzing" disappeared). Tests that
assert the PLACEHOLDER dots therefore mark the item as actively analyzing;
tests about a finished card assert the measured set (or none).
"""

from __future__ import annotations

from tabs.image_gallery.models import ActivityPhase


def mark_analyzing(item, *, source: str = "local"):
    """Mark *item* QUEUED for analysis (same source the pulse/pill reads)."""
    from tabs.image_gallery.services.activity import set_activity

    set_activity(item, ActivityPhase.QUEUED, source)
    return item
