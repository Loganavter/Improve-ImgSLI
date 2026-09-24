"""Gallery session-slot actions — Wave 1 (plan-gallery-redux-2026-09-24).

All payloads are plain paths/ids/scalars (no pixmaps, no workers, no
tokens). Reduced by the gallery tab-owned slot reducer against the
``gallery`` session slot; emitted with scope ``"gallery"``.

Batching: multi-mutations go through ``Store.transact([...],
scope="gallery")``; per-item async completions coalesce to ONE action per
event-loop turn (e.g. a single ``GalleryThumbnailsReady`` carrying every
thumbnail that landed since the last turn).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.state_management.action_base import Action, ActionType


def _norm_entries(entries) -> list[tuple[str, int]]:
    """Normalize ``entries`` to ``[(path_str, mtime_ns), ...]``.

    Accepts ``(path, mtime_ns)`` tuples/lists, ``{"path":..,"mtime_ns":..}``
    dicts, or bare path-likes (mtime 0). Pure helper — no Qt, no I/O.
    """
    norm: list[tuple[str, int]] = []
    for e in entries or []:
        if isinstance(e, dict):
            norm.append((str(e.get("path", "")), int(e.get("mtime_ns", 0) or 0)))
        elif isinstance(e, (tuple, list)) and len(e) == 2:
            norm.append((str(e[0]), int(e[1] or 0)))
        else:
            norm.append((str(e), 0))
    return norm


def _norm_paths(paths) -> list[str]:
    return [str(p) for p in paths or []]


@dataclass
class GalleryPoolOpened(Action):
    """Folder scan landed: replace the whole pool under a folder context."""

    folder: str | None = None
    entries: list = field(default_factory=list)
    type: str = field(default=ActionType.GALLERY_POOL_OPENED.value, kw_only=True)

    def __post_init__(self):
        if self.folder is not None:
            self.folder = str(self.folder)
        self.entries = _norm_entries(self.entries)

    def get_payload(self):
        return {"folder": self.folder, "items": len(self.entries)}


@dataclass
class GalleryPathsAppended(Action):
    """Explicit file drop: append truly-new paths, dedup by path."""

    entries: list = field(default_factory=list)
    type: str = field(default=ActionType.GALLERY_PATHS_APPENDED.value, kw_only=True)

    def __post_init__(self):
        self.entries = _norm_entries(self.entries)

    def get_payload(self):
        return {"items": len(self.entries)}


@dataclass
class GalleryPoolReplaced(Action):
    """Wipe-and-replace (explicit pick / replace drop)."""

    folder: str | None = None
    entries: list = field(default_factory=list)
    type: str = field(default=ActionType.GALLERY_POOL_REPLACED.value, kw_only=True)

    def __post_init__(self):
        if self.folder is not None:
            self.folder = str(self.folder)
        self.entries = _norm_entries(self.entries)

    def get_payload(self):
        return {"folder": self.folder, "items": len(self.entries)}


@dataclass
class GalleryItemsRemoved(Action):
    """Remove pool members by path string."""

    paths: list = field(default_factory=list)
    type: str = field(default=ActionType.GALLERY_ITEMS_REMOVED.value, kw_only=True)

    def __post_init__(self):
        self.paths = _norm_paths(self.paths)

    def get_payload(self):
        return {"items": len(self.paths)}


@dataclass
class GallerySelectionSet(Action):
    """Wholesale selection (ordered path-id list). Not undoable (view)."""

    selected_ids: list = field(default_factory=list)
    type: str = field(default=ActionType.GALLERY_SELECTION_SET.value, kw_only=True)

    def __post_init__(self):
        self.selected_ids = _norm_paths(self.selected_ids)

    def get_payload(self):
        return {"selected": len(self.selected_ids)}


@dataclass
class GalleryFilterSet(Action):
    """Filter query text. Not undoable (view)."""

    filter_text: str = ""
    type: str = field(default=ActionType.GALLERY_FILTER_SET.value, kw_only=True)

    def __post_init__(self):
        self.filter_text = str(self.filter_text or "")

    def get_payload(self):
        return {"filter_text": self.filter_text}


@dataclass
class GalleryThumbnailsReady(Action):
    """Coalesced thumbnail completions: [(path, status), ...].

    ONE action per event-loop turn (never one dispatch per item).
    Progress action — NOT undoable.
    """

    ready: list = field(default_factory=list)
    type: str = field(default=ActionType.GALLERY_THUMBNAILS_READY.value, kw_only=True)

    def __post_init__(self):
        norm: list[tuple[str, str]] = []
        for e in self.ready or []:
            if isinstance(e, (tuple, list)) and len(e) == 2:
                norm.append((str(e[0]), str(e[1])))
            elif isinstance(e, dict):
                norm.append((str(e.get("path", "")), str(e.get("status", ""))))
        self.ready = norm

    def get_payload(self):
        return {"items": len(self.ready)}


@dataclass
class GalleryTriageFinished(Action):
    """Triage pass completed: wholesale summary + per-path ranks."""

    triage_state: str = "done"
    mode: str | None = None
    source_path: str | None = None
    ranks: dict = field(default_factory=dict)
    type: str = field(default=ActionType.GALLERY_TRIAGE_FINISHED.value, kw_only=True)

    def __post_init__(self):
        self.triage_state = str(self.triage_state or "done")
        if self.mode is not None:
            self.mode = str(self.mode)
        if self.source_path is not None:
            self.source_path = str(self.source_path)
        self.ranks = {str(k): (None if v is None else int(v)) for k, v in (self.ranks or {}).items()}

    def get_payload(self):
        return {
            "triage_state": self.triage_state,
            "mode": self.mode,
            "source_path": self.source_path,
            "ranked": len(self.ranks),
        }


__all__ = [
    "GalleryPoolOpened",
    "GalleryPathsAppended",
    "GalleryPoolReplaced",
    "GalleryItemsRemoved",
    "GallerySelectionSet",
    "GalleryFilterSet",
    "GalleryThumbnailsReady",
    "GalleryTriageFinished",
]
