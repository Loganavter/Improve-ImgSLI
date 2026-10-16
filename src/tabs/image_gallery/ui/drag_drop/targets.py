"""Series-band / drop-target geometry for the gallery drag & drop router.

Split out of the router (formerly the single file ``ui/drag_drop.py``) per
``CODE_PATTERNS.md`` thin owner + ``ui/`` modules: these are plain functions
taking the owning widget as their first argument, resolving the drop target
(series header, card, or full-width section band) in OWNER space. The router
in ``ui/drag_drop/__init__.py`` re-exports every name here so
``tabs.image_gallery.ui.drag_drop`` keeps its full surface (names unchanged).

Audit-Meta: pattern=thin-owner-target size=exempt reason="drop-target geometry resolvers split out of the drag_drop router; one owner-space hit-test concern (headers/cards/bands) pinned as a unit"
"""

from __future__ import annotations

from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log

_UNGROUPED_HEADER_NAME = "GallerySeriesHeader_ungrouped"


def _event_pos(event):
    """Cursor position in widget coords (Qt6 position() with Qt5 fallback)."""
    try:
        return event.position().toPoint()
    except Exception:
        pass
    try:
        return event.pos()
    except Exception:
        pass
    try:
        from PySide6.QtCore import QPoint as _QPoint

        return _QPoint(0, 0)
    except Exception:
        return None


def _owner_space_pos(owner, event, receiver=None):
    """Cursor position in OWNER coords (Wave E fix).

    During ``QDrag.exec`` the app-visible ``QCursor.pos()`` is FROZEN on
    this stack (proven by move-trace: cursor fixed while ``QDragMoveEvent``
    positions advance) — every cursor-derived source (``mapFromGlobal``,
    ``widgetAt``) resolves the drag ORIGIN, not the drop point. So no
    cursor source is used here at all: the event position travels with the
    real pointer. When the receiver is known (zone-filter forwarding passes
    ``watched``), map through the receiver chain into owner space (pure
    local mapping — no screen frame, per the maximized-window precedent);
    otherwise the receiver is the owner itself (widget accepts drops
    anywhere) and the event pos is already owner-space.
    """
    try:
        pos = event.position().toPoint()
    except Exception:
        try:
            pos = event.pos()
        except Exception:
            return None
    if pos is None:
        return None
    if receiver is not None:
        try:
            if receiver is not owner:
                return receiver.mapTo(owner, pos)
        except Exception:
            pass
    return pos


def _series_for_card_path(grid, path: str):
    """Cluster series id for a card path (model truth, Wave D helper).

    Returns ``(resolved, series_id)``: membership in ``grid._series``
    clusters first, UNGROUPED-tail membership (None) second. Unplaced paths
    report ``(False, None)`` — callers fall back to the card's live attr.
    """
    try:
        clusters = list(getattr(grid, "_series", None) or [])
    except Exception:
        clusters = []
    for idx, entry in enumerate(clusters):
        try:
            members = list(entry.members) if hasattr(entry, "members") else list(entry)
        except Exception:
            continue
        try:
            hit = any(str(getattr(m, "path", "")) == path for m in members)
        except Exception:
            hit = False
        if not hit:
            continue
        try:
            first_sid = getattr(members[0], "series_id", None)
            sid = str(first_sid) if first_sid is not None else None
        except Exception:
            sid = None
        if sid is None:
            try:
                sid = _series_id_for_index(grid, idx)
            except Exception:
                sid = None
        return (True, sid)
    try:
        tail = list(getattr(grid, "_ungrouped", None) or [])
        if any(str(getattr(m, "path", "")) == path for m in tail):
            return (True, None)
    except Exception:
        pass
    return (False, None)


def _owner_hit_pos(owner, event, receiver=None):
    """Owner-space pos for header hit-testing (Wave E, event-only).

    Cursor sources are poisoned during ``QDrag.exec`` (frozen
    ``QCursor.pos()`` — move-trace proven), so the event position is the
    only live truth. ``receiver`` (when the caller knows it, e.g. zone
    forwarding) is mapped into owner space; otherwise the event pos is
    already owner-space (widget accepts drops anywhere).
    """
    return _owner_space_pos(owner, event, receiver)


def _section_bands(owner, headers):
    """Section header bands ``[(top_y, header)]`` top-to-bottom (owner space).

    A series owns everything from its header down to the next header —
    full width, cards, gaps, collapsed empties. Sorted by visual top so
    recycled/reordered header widgets cannot skew the order.
    """
    out: list = []
    try:
        from PySide6.QtCore import QPoint as _QPoint

        for hdr in list(headers or []):
            try:
                out.append((hdr.mapTo(owner, _QPoint(0, 0)).y(), hdr))
            except Exception:
                continue
    except Exception:
        return []
    try:
        out.sort(key=lambda t: t[0])
    except Exception:
        pass
    return out


def _series_id_for_header(grid, headers, hdr) -> tuple[bool, str | None]:
    """Series id for one header widget (True = resolved, even to None).

    UNGROUPED tail → ``(True, None)``; ``GallerySeriesHeader_<int>`` →
    cluster index; anything else → positional fallback (series sections
    precede the UNGROUPED tail), ``(False, None)`` when unresolvable.
    """
    try:
        name = str(hdr.objectName() or "")
    except Exception:
        return (False, None)
    if name == _UNGROUPED_HEADER_NAME or name.endswith("_ungrouped"):
        return (True, None)
    index: int | None = None
    try:
        prefix = "GallerySeriesHeader_"
        if name.startswith(prefix):
            index = int(name[len(prefix):])
    except Exception:
        index = None
    if index is None:
        try:
            hdr_pos = list(headers or []).index(hdr)
        except Exception:
            return (False, None)
        try:
            n_series = len(list(getattr(grid, "_series", None) or []))
        except Exception:
            n_series = 0
        if hdr_pos < n_series:
            index = hdr_pos
        else:
            return (True, None)
    try:
        return (True, _series_id_for_index(grid, index))
    except Exception:
        return (False, None)


def _section_band_target(owner, grid, headers, pos) -> tuple[bool, str | None, object]:
    """Band fallback: full-width section body down to the next series.

    Headers and cards miss (gaps, margins, collapsed empties, area below
    the last row) — the band from this section's header top to the next
    header top still belongs to it; the last band runs to the owner
    bottom. Above the first header there is no section → not found (the
    caller keeps its UNGROUPED fallback). Returns
    ``(found, series_id, header)``.
    """
    try:
        bands = _section_bands(owner, headers)
    except Exception:
        return (False, None, None)
    if not bands or pos is None:
        return (False, None, None)
    try:
        y = pos.y()
    except Exception:
        return (False, None, None)
    if y < bands[0][0]:
        return (False, None, None)
    chosen = bands[0][1]
    for top_y, hdr in bands:
        if top_y <= y:
            chosen = hdr
        else:
            break
    try:
        ok, sid = _series_id_for_header(grid, headers, chosen)
    except Exception:
        return (False, None, None)
    if not ok:
        return (False, None, None)
    return (True, sid, chosen)


def _series_id_for_index(grid, index: int) -> str | None:
    """Series id string for cluster *index* (first member id, else fallback)."""
    try:
        clusters = list(getattr(grid, "_series", None) or [])
        entry = clusters[index] if 0 <= int(index) < len(clusters) else None
    except Exception:
        entry = None
    members: list = []
    try:
        if entry is not None:
            if hasattr(entry, "members"):
                members = list(getattr(entry, "members", None) or [])
            elif isinstance(entry, (list, tuple)):
                members = list(entry)
    except Exception:
        members = []
    for m in members:
        try:
            sid = getattr(m, "series_id", None)
        except Exception:
            sid = None
        if sid is not None:
            try:
                return str(sid)
            except Exception:
                pass
    try:
        return f"series_{int(index) + 1}"
    except Exception:
        return None


def _dump_drop_geometry(owner, grid, headers, pos) -> None:
    """Firehose probe (Wave D diagnosis): headers/cards geometry at drop.

    Session-only, gated by the gallery debug flag (DEBUGGING.md rule 5:
    separate unfiltered flag-lines, never mixed into curated verdicts).
    Hypothesis under test: the drop resolves the wrong series because the
    header/card geometry or name→id mapping does not match the visible
    order. Kill condition: a drop whose dumped matching rect is the header
    the user aimed at, with the expected id.
    """
    try:
        from tabs.image_gallery.debug import gallery_dnd_debug_enabled as _gate
        if not _gate():
            return
    except Exception:
        return
    try:
        from PySide6.QtCore import QPoint as _QPoint
        from PySide6.QtCore import QRect as _QRect

        lines = ["drop-geometry pos=%s" % (pos,)]
        for i, hdr in enumerate(headers or []):
            try:
                top = hdr.mapTo(owner, _QPoint(0, 0))
                rect = _QRect(top, hdr.size())
                lines.append(
                    "hdr[%d] name=%r rect=%s hit=%s visible=%s" % (
                        i, hdr.objectName(),
                        "(%d,%d %dx%d)" % (rect.x(), rect.y(), rect.width(), rect.height()),
                        bool(rect.contains(pos)) if pos is not None else "?",
                        bool(hdr.isVisibleTo(owner)) if hasattr(hdr, "isVisibleTo") else "?",
                    )
                )
            except Exception as e:
                lines.append("hdr[%d] map failed: %r" % (i, e))
        try:
            cards = dict(getattr(grid, "_cards_by_path", None) or {})
        except Exception:
            cards = {}
        for key, card in cards.items():
            try:
                top = card.mapTo(owner, _QPoint(0, 0))
                rect = _QRect(top, card.size())
                lines.append(
                    "card %s rect=%s hit=%s visible=%s" % (
                        str(key).split("/")[-1],
                        "(%d,%d %dx%d)" % (rect.x(), rect.y(), rect.width(), rect.height()),
                        bool(rect.contains(pos)) if pos is not None else "?",
                        bool(card.isVisibleTo(owner)) if hasattr(card, "isVisibleTo") else "?",
                    )
                )
            except Exception as e:
                lines.append("card %s map failed: %r" % (key, e))
        try:
            order = []
            for entry in list(getattr(grid, "_series", None) or []):
                members = (
                    list(entry.members) if hasattr(entry, "members") else list(entry)
                )
                first = getattr(members[0], "series_id", None) if members else None
                order.append("%s:%d" % (first, len(members)))
            lines.append("clusters=%s" % (order,))
        except Exception as e:
            lines.append("clusters unreadable: %r" % e)
        for ln in lines:
            _dnd_log(ln)
    except Exception:
        pass


def series_target_at(owner, pos) -> tuple[bool, str | None]:
    """Resolve the drop-target series under *pos* (OWNER coords).

    *pos* must already be in owner space — callers pass
    ``_owner_hit_pos(owner, event)`` (live cursor mapped into the owner,
    receiver-relative pos as synthetic fallback),
    never the raw receiver-relative ``_event_pos``. Headers are compared via
    ``hdr.mapTo(owner)``, so owner space is the only correct frame.

    Returns ``(handled, series_id)``: ``series_id`` is the header cluster id
    under the cursor, or None for the UNGROUPED tail (forced UNGROUPED —
    also the fallback when the drop lands on no header). ``handled`` False
    means "no series chrome to drop onto" (empty pool / flat grid) — the
    caller must ignore the drop, never route it externally.
    """
    grid = getattr(owner, "_grid_view", None)
    if grid is None:
        # Bare doubles / storeless contexts: no chrome to hit-test, but
        # the controller still filters to pool members — route UNGROUPED.
        return (True, None)
    try:
        headers = list(getattr(grid, "_series_headers", None) or [])
    except Exception:
        headers = []
    if not headers or pos is None:
        return (False, None)
    _dump_drop_geometry(owner, grid, headers, pos)
    try:
        from PySide6.QtCore import QPoint as _QPoint
        from PySide6.QtCore import QRect as _QRect
    except Exception:
        return (False, None)
    for hdr_pos, hdr in enumerate(headers):
        try:
            top = hdr.mapTo(owner, _QPoint(0, 0))
            rect = _QRect(top, hdr.size())
            if not rect.contains(pos):
                continue
        except Exception:
            continue
        try:
            ok, sid = _series_id_for_header(grid, headers, hdr)
        except Exception:
            continue
        if ok:
            return (True, sid)
        continue
    # No header hit: fall back to the card under the cursor (Wave D). Series
    # bodies are ~99% cards — drops land on cards, not on thin headers.
    try:
        found, card_sid = _card_hit_series(owner, grid, pos)
    except Exception:
        found, card_sid = False, None
    if found:
        return (True, card_sid)
    # Band fallback (Wave E): full-width section body down to the next
    # series — gaps, margins, collapsed empties resolve to the section.
    try:
        found, band_sid, _band_hdr = _section_band_target(owner, grid, headers, pos)
    except Exception:
        found, band_sid = False, None
    if found:
        return (True, band_sid)
    return (True, None)


def _header_button(header):
    """Header button for drop-target highlight (or None).

    Prefers the toolkit header ``Button`` by object name
    (``GallerySeriesHeaderBtn_*`` — it owns the painter layers, but has no
    Qt ``setDown``); falls back to the first setDown-capable child
    (legacy/PushButton doubles in tests).
    """
    try:
        from PySide6.QtWidgets import QWidget as _QW

        children = list(header.findChildren(_QW))
    except Exception:
        return None
    try:
        for child in children:
            try:
                name = str(child.objectName() or "")
            except Exception:
                continue
            if name.startswith("GallerySeriesHeaderBtn_"):
                return child
    except Exception:
        pass
    try:
        for child in children:
            try:
                if callable(getattr(child, "setDown", None)):
                    return child
            except Exception:
                continue
    except Exception:
        pass
    return None


def _clear_series_highlight(owner) -> None:
    """Drop the series-header drop-target highlight (fail-soft)."""
    try:
        current = getattr(owner, "_series_drop_target", None)
    except Exception:
        current = None
    if current is None:
        return
    try:
        owner._series_drop_target = None
    except Exception:
        pass
    header, btn, was_enabled = current if isinstance(current, tuple) else (current, None, None)
    if btn is None:
        try:
            btn = _header_button(header)
        except Exception:
            btn = None
    try:
        if btn is not None:
            try:
                down = getattr(btn, "setDown", None)
                if callable(down):
                    down(False)
            except Exception:
                pass
            try:
                btn._gallery_drop_target = False  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                btn.update()
            except Exception:
                pass
    except Exception:
        pass
    try:
        if was_enabled is False and btn is not None:
            btn.setEnabled(False)
    except Exception:
        pass


def _set_series_highlight(owner, header) -> None:
    """Highlight *header* as the live drop target (pressed-state accent).

    Reuses the header button's own pressed visuals — no QSS, no colors,
    no new API. Remembers the previous target to restore it. Fail-soft:
    headers whose button cannot render pressed state simply stay plain.
    """
    try:
        current = getattr(owner, "_series_drop_target", None)
        cur_header = current[0] if isinstance(current, tuple) else current
        if cur_header is header:
            return
    except Exception:
        pass
    _clear_series_highlight(owner)
    if header is None:
        return
    try:
        _dnd_log(
            "series highlight -> %s",
            getattr(header, "objectName", lambda: "?")(),
        )
    except Exception:
        pass
    btn = _header_button(header)
    was_enabled: bool | None = None
    try:
        if btn is not None:
            try:
                was_enabled = bool(btn.isEnabled())
            except Exception:
                was_enabled = None
            if was_enabled is False:
                # The UNGROUPED header button is disabled: enable it for the
                # drag duration (clicks cannot land mid-drag) so the pressed
                # state paints, then restore on clear.
                btn.setEnabled(True)
            # setDown is Qt-widget API: toolkit Buttons do not have it —
            # guard so the flag + update below always run (Wave E layer
            # reads the flag, not the pressed state).
            try:
                down = getattr(btn, "setDown", None)
                if callable(down):
                    down(True)
            except Exception:
                pass
            # Wave E color landing indicator (painter layer on the header
            # button reads this flag; reset in _clear_series_highlight).
            try:
                btn._gallery_drop_target = True  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                btn.update()
            except Exception:
                pass
    except Exception:
        pass
    try:
        owner._series_drop_target = (header, btn, was_enabled)
    except Exception:
        pass


def _card_path(card, fallback_key=None):
    """Filesystem path string for a gallery card (duck-typed, never raises)."""
    try:
        item = getattr(card, "_gallery_item", None)
        path = getattr(item, "path", None) if item is not None else None
        if path is None and card is not None and hasattr(card, "property"):
            try:
                path = card.property("gallery_path")
            except Exception:
                path = None
        if path is None or (not str(path) and fallback_key is not None):
            path = fallback_key
        return str(path) if path is not None else ""
    except Exception:
        try:
            return str(fallback_key) if fallback_key is not None else ""
        except Exception:
            return ""


def _card_hit_series(owner, grid, pos) -> tuple[bool, str | None]:
    """Series id of the card under *pos* (OWNER coords).

    Returns ``(found, series_id)``: ``series_id`` is the owning cluster id,
    or None for UNGROUPED-tail cards. ``found`` False means no card under
    the cursor. Model truth first (cluster membership by path in
    ``grid._series`` / ``grid._ungrouped``), live card attr second. Dropping
    onto a dragged card itself resolves its own series — the controller
    no-op guard then skips the retriage, so no exclusion is needed here.
    """
    if grid is None or pos is None:
        return (False, None)
    try:
        cards = getattr(grid, "_cards_by_path", None) or {}
        cards = dict(cards)
    except Exception:
        return (False, None)
    if not cards:
        return (False, None)
    try:
        from PySide6.QtCore import QPoint as _QPoint
        from PySide6.QtCore import QRect as _QRect

        for key, card in cards.items():
            try:
                top = card.mapTo(owner, _QPoint(0, 0))
                if not _QRect(top, card.size()).contains(pos):
                    continue
            except Exception:
                continue
            path = _card_path(card, key)
            sid: str | None = None
            resolved = False
            try:
                resolved, sid = _series_for_card_path(grid, path)
            except Exception:
                resolved, sid = False, None
            if not resolved:
                try:
                    item = getattr(card, "_gallery_item", None)
                    live = getattr(item, "series_id", None)
                    sid = str(live) if live is not None else None
                    resolved = True
                except Exception:
                    pass
            if resolved:
                return (True, sid)
            return (True, None)
    except Exception:
        pass
    return (False, None)


def _header_for_series(grid, headers, series_id):
    """Header widget for *series_id* (None = UNGROUPED header), or None."""
    try:
        headers = list(headers or [])
    except Exception:
        return None
    if not headers:
        return None
    try:
        target = str(series_id) if series_id is not None else None
    except Exception:
        target = None
    for hdr in headers:
        try:
            name = str(getattr(hdr, "objectName", lambda: "")() or "")
        except Exception:
            name = ""
        if target is None:
            if name == _UNGROUPED_HEADER_NAME or name.endswith("_ungrouped"):
                return hdr
        else:
            try:
                idx = headers.index(hdr)
            except Exception:
                continue
            try:
                if _series_id_for_index(grid, idx) == target:
                    return hdr
            except Exception:
                continue
    return None


def _header_at(owner, pos):
    """Header widget under *pos* (OWNER coords, see ``series_target_at``).

    Headers first; on a miss, the card under the cursor resolves to its
    series' header (Wave D — drops land on cards, highlight must follow);
    on a card miss, the section band resolves to its header (Wave E —
    full-width body down to the next series).
    """
    grid = getattr(owner, "_grid_view", None)
    if grid is None or pos is None:
        return None
    try:
        headers = list(getattr(grid, "_series_headers", None) or [])
    except Exception:
        headers = []
    if headers:
        try:
            from PySide6.QtCore import QPoint as _QPoint
            from PySide6.QtCore import QRect as _QRect

            for hdr in headers:
                try:
                    top = hdr.mapTo(owner, _QPoint(0, 0))
                    if _QRect(top, hdr.size()).contains(pos):
                        return hdr
                except Exception:
                    continue
        except Exception:
            pass
    try:
        found, card_sid = _card_hit_series(owner, grid, pos)
    except Exception:
        found = False
    if found:
        try:
            return _header_for_series(grid, headers, card_sid)
        except Exception:
            pass
    try:
        found, _band_sid, band_hdr = _section_band_target(owner, grid, headers, pos)
    except Exception:
        return None
    return band_hdr if found else None


def _grid_has_headers(owner) -> bool:
    try:
        grid = getattr(owner, "_grid_view", None)
        return bool(grid is not None and list(getattr(grid, "_series_headers", None) or []))
    except Exception:
        return False
