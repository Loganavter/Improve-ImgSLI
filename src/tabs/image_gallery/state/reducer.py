"""Gallery slot reducer — Wave 1 (plan-gallery-redux-2026-09-24).

Pure functions only: every branch returns a NEW ``GallerySlotState`` via
``dataclasses.replace`` (new item list, new item instances on change) and
never mutates the incoming state. Unknown actions (including every
non-gallery action the ``RootReducer`` fans out to all slot reducers)
return the IDENTICAL state so the dispatcher's ``is``-based no-op
detection skips history + emit.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.state_management.gallery_actions import (
    GalleryFilterSet,
    GalleryItemsRemoved,
    GalleryPathsAppended,
    GalleryPoolOpened,
    GalleryPoolReplaced,
    GallerySelectionSet,
    GalleryThumbnailsReady,
    GalleryTriageFinished,
)
from tabs.image_gallery.state.models import (
    GalleryItemMeta,
    GallerySlotState,
    fresh_gallery_slot_state,
)


def _pool_index(state: GallerySlotState) -> dict[str, int]:
    return {it.path: i for i, it in enumerate(state.items)}


class GallerySlotReducer:
    @staticmethod
    def _replace_pool(
        state: GallerySlotState,
        folder: str | None,
        entries: list[tuple[str, int]],
    ) -> GallerySlotState:
        items = [
            GalleryItemMeta(path=path, mtime_ns=mtime, status="not_loaded", rank=None)
            for path, mtime in entries
        ]
        return replace(state, folder=folder, items=items, selection=[])

    @staticmethod
    def reduce(state: Any, action: Any) -> Any:
        if state is None:
            state = fresh_gallery_slot_state()
        if isinstance(action, GalleryPoolOpened):
            return GallerySlotReducer._replace_pool(state, action.folder, action.entries)
        if isinstance(action, GalleryPoolReplaced):
            return GallerySlotReducer._replace_pool(state, action.folder, action.entries)
        if isinstance(action, GalleryPathsAppended):
            if not action.entries:
                return state
            known = {it.path for it in state.items}
            fresh: list[GalleryItemMeta] = []
            for path, mtime in action.entries:
                if path in known:
                    continue
                known.add(path)
                fresh.append(
                    GalleryItemMeta(
                        path=path, mtime_ns=mtime, status="not_loaded", rank=None
                    )
                )
            if not fresh:
                return state
            return replace(state, items=[*state.items, *fresh])
        if isinstance(action, GalleryItemsRemoved):
            if not action.paths:
                return state
            doomed = set(action.paths)
            if not any(it.path in doomed for it in state.items):
                return state
            items = [it for it in state.items if it.path not in doomed]
            selection = [sid for sid in state.selection if sid not in doomed]
            return replace(state, items=items, selection=selection)
        if isinstance(action, GallerySelectionSet):
            seen: set[str] = set()
            ordered: list[str] = []
            for sid in action.selected_ids:
                if sid not in seen:
                    seen.add(sid)
                    ordered.append(sid)
            if ordered == list(state.selection):
                return state
            return replace(state, selection=ordered)
        if isinstance(action, GalleryFilterSet):
            if state.filter_text == action.filter_text:
                return state
            return replace(state, filter_text=action.filter_text)
        if isinstance(action, GalleryThumbnailsReady):
            if not action.ready:
                return state
            index = _pool_index(state)
            changed = {
                path: status
                for path, status in action.ready
                if path in index and state.items[index[path]].status != status
            }
            if not changed:
                return state
            items = [
                replace(it, status=changed[it.path]) if it.path in changed else it
                for it in state.items
            ]
            return replace(state, items=items)
        if isinstance(action, GalleryTriageFinished):
            ranks = action.ranks or {}
            items = [
                replace(it, rank=ranks.get(it.path))
                for it in state.items
            ]
            ranks_changed = any(
                new.rank != old.rank for new, old in zip(items, state.items)
            )
            if (
                not ranks_changed
                and state.triage_state == action.triage_state
                and state.mode == action.mode
                and state.source_path == action.source_path
            ):
                return state
            if not ranks_changed:
                items = list(state.items)
            return replace(
                state,
                items=items,
                triage_state=action.triage_state,
                mode=action.mode,
                source_path=action.source_path,
            )
        return state
