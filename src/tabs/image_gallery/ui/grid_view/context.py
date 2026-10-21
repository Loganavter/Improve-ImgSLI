"""Card + series context-menu dispatch (grid_view package, plan C1)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Layer, OverlayScrollArea

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import (
    GALLERY_CARD_H,
    GALLERY_CARD_W,
    apply_gallery_selection,
    build_gallery_card,
    gallery_selection_accent,
    update_gallery_card,
)
from tabs.image_gallery.ui.card.activity_pulse import ActivityPulse
from tabs.image_gallery.ui.list.card import (
    LIST_CARD_H,
    _bind_list_row,
    build_gallery_list_card,
    update_gallery_list_card,
)
from ui.widgets.shelf import OpaqueFillHost, apply_opaque_widget_fill

logger = logging.getLogger("ImproveImgSLI")

def _section_members(entry) -> list:
    """Member list of one cluster (Series dataclass or plain list)."""
    try:
        if hasattr(entry, "members"):
            return list(getattr(entry, "members", None) or [])
        if isinstance(entry, (list, tuple)):
            return list(entry)
    except Exception:
        pass
    return []

def _cluster_series_id(cluster) -> str:
    """The owning series id of a member cluster (stable across all members)."""
    for member in cluster or ():
        sid = getattr(member, "series_id", None)
        if sid:
            return str(sid)
    return ""

def _header_button(hdr):
    """Focusable ``Button`` inside a series/tail header container, or None."""
    if hdr is None:
        return None
    if isinstance(hdr, Button):
        return hdr
    try:
        return hdr.findChild(Button)
    except Exception:
        return None

def _handle_context_menu(view, path: Path | None) -> None:
    self = view
    if callable(self._on_context_menu) and path is not None:
        try:
            self._on_context_menu(path)
        except Exception:
            pass

def _handle_series_context(view, anchor, index, local_pos=None) -> None:
    """Series-header right-click → host callback.

    Host gets ``(index, anchor, paths, label, series_id, global_pos)``:
    ``series_id`` is the session-stable ``series_<n>`` of the cluster's
    members (``None`` when unknown), ``global_pos`` the popup anchor in
    screen coordinates.
    """
    self = view
    if not callable(self._on_series_context_menu):
        return
    try:
        members = list((self._series or [])[int(index)])
    except Exception:
        members = []
    paths = []
    series_id = None
    for it in members:
        try:
            paths.append(it.path)
        except Exception:
            continue
        if series_id is None:
            try:
                sid = getattr(it, "series_id", None)
            except Exception:
                sid = None
            if sid:
                series_id = str(sid)
    # Pass the series NAME only (the hub), not the full header chrome
    # ("SERIES 1 · … · N VARIANTS") — that repeated the grid header in
    # the flyout.
    label = ""
    try:
        idx = int(index)
        hub = self._hub_names[idx] if idx < len(self._hub_names) else None
        label = str(hub or self._series_header_labels.get(idx, "") or "")
    except Exception:
        label = ""
    global_pos = None
    try:
        if local_pos is not None:
            global_pos = anchor.mapToGlobal(local_pos)
    except Exception:
        global_pos = None
    if global_pos is None:
        try:
            from PySide6.QtGui import QCursor

            global_pos = QCursor.pos()
        except Exception:
            global_pos = None
    try:
        self._on_series_context_menu(
            int(index), anchor, tuple(paths), label, series_id, global_pos
        )
    except Exception:
        pass
