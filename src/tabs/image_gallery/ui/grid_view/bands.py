"""Side-by-side series bands + center splitter (grid_view package, plan C1)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Label, Layer, OverlayScrollArea

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

from tabs.image_gallery.ui.grid_view import GRID_BAND_MIN_TOTAL, GRID_COLUMNS, VIEW_LIST

from .layers import _BandSeparatorHandle

def _bands_active(view) -> bool:
    """True when the last series layout split sections into two bands."""
    self = view
    try:
        return self._band_state is not None
    except Exception:
        return False

def _plan_bands(view, sections: list[dict]) -> list[tuple[list[dict], int, int]]:
    """Split *sections* into layout bands.

    Returns ``[(sections, band_cols, col_offset), ...]`` — one entry for
    the stacked full-width band, two when the viewport fits side-by-side
    series (first section left, the rest right, separator column between).
    """
    self = view
    try:
        total = int(self.grid_columns)
    except Exception:
        total = GRID_COLUMNS
    if self._view_mode == VIEW_LIST or total < GRID_BAND_MIN_TOTAL or len(sections) < 2:
        return [(list(sections), int(total), 0)]
    left = self._split_left
    try:
        left = int(left) if left is not None else int(total // 2)
    except Exception:
        left = int(total // 2)
    left = max(2, min(int(total) - 3, int(left)))
    right = int(total) - int(left) - 1  # one column for the separator
    if left < 2 or right < 2:
        return [(list(sections), int(total), 0)]
    return [([sections[0]], int(left), 0), (list(sections[1:]), int(right), int(left) + 1)]

def _plan_band_entries(
    view,
    subset: list[dict],
    band_cols: int,
    col_off: int,
    base_row: int,
    headers: list,
    hdr_start: int,
) -> tuple[list[tuple], int, int]:
    """Plan entries for one band; returns (entries, rows_used, hdr_next)."""
    self = view
    entries: list[tuple] = []
    row = int(base_row)
    hi = int(hdr_start)
    for sec in subset:
        try:
            header = headers[hi]
            hi += 1
        except Exception:
            continue
        entries.append((header, row, int(col_off), 1, int(band_cols)))
        row += 1
        if sec.get("collapsed"):
            continue
        for pos, item in enumerate(sec.get("items") or []):
            try:
                card = self._cards_by_path.get(str(item.path))
            except Exception:
                card = None
            if card is None:
                continue
            try:
                r, c = divmod(int(pos), max(1, int(band_cols)))
            except Exception:
                r, c = int(pos), 0
            entries.append((card, row + r, int(col_off) + c, 1, 1))
        try:
            n = len(sec.get("items") or [])
            rows_needed = (n + int(band_cols) - 1) // int(band_cols) if n else 0
        except Exception:
            rows_needed = 0
        row += int(rows_needed)
    return entries, int(row - base_row), int(hi)

def _ensure_band_separator(view):
    """Lazily create the draggable center-splitter handle."""
    self = view
    sep = getattr(self, "_band_separator", None)
    try:
        import shiboken6

        if sep is not None and not shiboken6.isValid(sep):
            sep = None
    except Exception:
        pass
    if sep is None:
        try:
            sep = _BandSeparatorHandle(self, self.items_host)
            self._band_separator = sep
        except Exception:
            return None
    return sep

def _hide_band_separator(view) -> None:
    self = view
    try:
        sep = getattr(self, "_band_separator", None)
        if sep is not None:
            try:
                self.items_layout.removeWidget(sep)
            except Exception:
                pass
            try:
                sep.hide()
            except Exception:
                pass
    except Exception:
        pass
    try:
        self._band_state = None
    except Exception:
        pass

def _nudge_split_by_px(view, dx: int) -> bool:
    """Shift the center split by a drag delta; True when replanned."""
    self = view
    try:
        if self._view_mode == VIEW_LIST or not self._bands_active():
            return False
        total = int(self._applied_columns)
        st = self._band_state or (total // 2, total - total // 2 - 1, total // 2)
        left = int(st[0])
        stride = self._grid_stride_px()
        if stride <= 0:
            return False
        step = int(round(float(dx) / float(stride)))
        if step == 0:
            return False
        want = max(2, min(int(total) - 3, int(left) + int(step)))
        if want == int(left):
            return False
        self._split_left = int(want)
        self._rebuild_series()
        return True
    except Exception:
        return False

def set_split_left(view, left_cols: int) -> None:
    """Programmatic center-split (tests / restore); replans when banded."""
    self = view
    try:
        total = int(self._applied_columns)
        self._split_left = max(2, min(int(total) - 3, int(left_cols)))
    except Exception:
        return
    try:
        if self._series is not None:
            self._rebuild_series()
    except Exception:
        pass

def nav_columns_for(view, path=None) -> int:
    """Up/Down arrow step for *path*'s band (band width when banded)."""
    self = view
    try:
        if self._view_mode == VIEW_LIST:
            return 1
        st = getattr(self, "_band_state", None)
        if not st:
            return int(self.grid_columns)
        left, right, sep_col = int(st[0]), int(st[1]), int(st[2])
        col = None
        if path is not None:
            try:
                card = self._cards_by_path.get(str(path))
                if card is not None:
                    idx = self.items_layout.indexOf(card)
                    if idx >= 0:
                        col = int(self.items_layout.getItemPosition(idx)[1])
            except Exception:
                col = None
        if col is None:
            return int(self.grid_columns)
        return int(left if col < sep_col else right)
    except Exception:
        try:
            return int(self.grid_columns)
        except Exception:
            return GRID_COLUMNS
