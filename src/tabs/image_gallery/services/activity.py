"""Per-item activity status derivation — pure (no Qt).

``activity_of`` answers "what is this card doing right now?" from the item's
transient explicit phase (fresh within ``ACTIVITY_TTL_S``) and, failing that,
from the persisted-side state (thumbnail / analysis status). Cards render the
result; the controller and AI hooks only ever call ``set_activity``.
"""

from __future__ import annotations

import time

from tabs.image_gallery.models import (
    ACTIVITY_SOURCES,
    ActivityPhase,
    AnalysisStatus,
    ThumbnailStatus,
)

ACTIVITY_TTL_S = 30.0

ACTIVE_PHASES: frozenset[str] = frozenset(
    {
        ActivityPhase.QUEUED.value,
        ActivityPhase.CLAIMED.value,
        ActivityPhase.ANALYZING.value,
        ActivityPhase.WAITING.value,
    }
)


def _enum_value(value) -> str:
    return str(getattr(value, "value", value) or "")


def _is_unreadable(item) -> bool:
    """Mirror of ``ui/card/regions._item_unreadable`` (pure copy, no Qt import)."""
    if _enum_value(getattr(item, "thumbnail_status", None)).lower() == ThumbnailStatus.ERROR.value:
        return True
    err = getattr(item, "analysis_error", None)
    if err:
        low = str(err).lower()
        if any(word in low for word in ("unreadable", "corrupt", "поврежд")):
            return True
    return False


def explicit_activity(item, now: float | None = None) -> tuple[str, str] | None:
    """The fresh explicit ``(phase, source)`` only, or None when absent/stale."""
    phase = getattr(item, "activity_phase", None)
    if not phase:
        return None
    at = float(getattr(item, "activity_at", 0.0) or 0.0)
    t = time.monotonic() if now is None else now
    if t - at > ACTIVITY_TTL_S:
        return None
    source = getattr(item, "activity_source", None) or "local"
    return (str(phase), str(source))


def activity_of(item, now: float | None = None) -> tuple[str, str] | None:
    """Derive ``(phase, source)`` for one item, or None when it is idle.

    Precedence: unreadable → fresh explicit phase → analysis error → local
    thumbnail loading → AI analysis status.
    """
    if item is None:
        return None
    if _is_unreadable(item):
        return (ActivityPhase.UNREADABLE.value, "local")
    explicit = explicit_activity(item, now=now)
    if explicit is not None:
        return explicit
    if getattr(item, "analysis_error", None):
        return (ActivityPhase.ERROR.value, "ai")
    if _enum_value(getattr(item, "thumbnail_status", None)) == ThumbnailStatus.LOADING.value:
        return (ActivityPhase.ANALYZING.value, "local")
    status = _enum_value(getattr(item, "analysis_status", None))
    if status == AnalysisStatus.PENDING.value:
        return (ActivityPhase.QUEUED.value, "ai")
    if status == AnalysisStatus.ERROR.value:
        return (ActivityPhase.ERROR.value, "ai")
    if status == AnalysisStatus.DONE.value:
        return (ActivityPhase.DONE.value, "ai")
    return None


def set_activity(item, phase, source) -> bool:
    """Stamp an explicit phase on ``item``. True when the phase/source changed.

    ``activity_at`` is always refreshed from ``time.monotonic()`` so a repeated
    phase keeps the TTL alive.
    """
    value = ActivityPhase(phase).value
    src = str(source)
    if src not in ACTIVITY_SOURCES:
        raise ValueError(f"unknown activity source: {source!r}")
    changed = (item.activity_phase != value) or (item.activity_source != src)
    item.activity_phase = value
    item.activity_source = src
    item.activity_at = time.monotonic()
    return changed


def clear_activity(item) -> None:
    """Drop the explicit phase so the item falls back to its persisted state."""
    item.activity_phase = None
    item.activity_source = None
    item.activity_at = 0.0
