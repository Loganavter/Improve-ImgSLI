"""Keyboard focus navigation for the card grid (grid_view package, plan C1).
Audit-Meta: pattern=thin-owner-target size=exempt reason="2D focus navigation is one concern moved out of the thin GalleryGridView owner (plan-gallery-split-2026-10-17 Part C1)"
"""

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

from tabs.image_gallery.ui.grid_view import GRID_COLUMNS, GRID_SPACING

from .drag_source import _card_drag_path
from .context import _header_button

def _focus_reason(view):
    """FocusReason for navigation grants (keyboard ring follows the manager)."""
    self = view
    try:
        from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

        return NavigationManager.get_instance().current_focus_reason()
    except Exception:
        return Qt.FocusReason.OtherFocusReason

def _live_cards_in_order(view) -> list:
    """Live, enabled cards in layout (row, col) display order.

    Series headers and recycled pool cards are excluded; banded layouts
    are read row-major (col offset orders left band before right band
    within a row), which is the same order ``_plan_band_entries`` lays
    them out.
    """
    self = view
    out: list[tuple[int, int, object]] = []
    for _path, card in list(getattr(self, "_cards_by_path", {}).items()):
        try:
            if not card.isEnabled():
                continue
        except Exception:
            continue
        try:
            idx = self.items_layout.indexOf(card)
        except Exception:
            idx = -1
        if idx < 0:
            continue
        try:
            pos = self.items_layout.getItemPosition(idx)
            r, c = int(pos[0]), int(pos[1])
        except Exception:
            r, c = int(idx), 0
        out.append((r, c, card))
    out.sort(key=lambda t: (t[0], t[1]))
    return [c for _r, _c, c in out]

def _live_headers_in_order(view) -> list:
    """Live, enabled series/tail header ``Button``s in layout (row, col) order."""
    self = view
    out: list[tuple[int, int, object]] = []
    for hdr in list(getattr(self, "_series_headers", []) or []):
        btn = _header_button(hdr)
        if btn is None:
            continue
        try:
            if not btn.isEnabled():
                continue
        except Exception:
            continue
        try:
            idx = self.items_layout.indexOf(hdr)
        except Exception:
            idx = -1
        if idx < 0:
            continue
        try:
            pos = self.items_layout.getItemPosition(idx)
            r, c = int(pos[0]), int(pos[1])
        except Exception:
            r, c = int(idx), 0
        out.append((r, c, btn))
    out.sort(key=lambda t: (t[0], t[1]))
    return [b for _r, _c, b in out]

def focused_card(view):
    """The live card holding Qt focus, or None (mirrors RecentItemsView)."""
    self = view
    try:
        from PySide6.QtWidgets import QApplication

        focused = QApplication.focusWidget()
    except Exception:
        return None
    if focused is None:
        return None
    for card in list(getattr(self, "_cards_by_path", {}).values()):
        if card is focused:
            return card
    return None

def focused_header(view):
    """The live series/tail header ``Button`` holding Qt focus, or None."""
    self = view
    try:
        from PySide6.QtWidgets import QApplication

        focused = QApplication.focusWidget()
    except Exception:
        return None
    if focused is None:
        return None
    for hdr in list(getattr(self, "_series_headers", []) or []):
        btn = _header_button(hdr)
        if btn is not None and (btn is focused or hdr is focused):
            return btn
    return None

def ensure_card_visible(view, card) -> None:
    """Scroll the focused card into the viewport (RecentItemsView parity)."""
    self = view
    try:
        from sli_ui_toolkit.managers import scaled_px as _scaled

        margin = int(_scaled(GRID_SPACING))
    except Exception:
        margin = 24
    try:
        self.scroll_area.ensureWidgetVisible(card, 0, margin)
    except Exception:
        pass

def focus_card(view, card, reason=None) -> bool:
    """Grant keyboard focus to *card* (or header Button) and reveal it.

    *reason* (a ``NavigationSection.focus_first/focus_last`` grant) wins;
    otherwise the ring modality comes from
    ``NavigationManager.current_focus_reason()`` — never a literal
    ``OtherFocusReason``.
    """
    self = view
    if card is None:
        return False
    if not isinstance(card, Button):
        btn = _header_button(card)
        if btn is not None:
            card = btn
    grant = reason if reason is not None else self._focus_reason()
    try:
        card.setFocus(grant)
    except Exception:
        try:
            card.setFocus(self._focus_reason())
        except Exception:
            return False
    self.ensure_card_visible(card)
    return True

def focus_first_card(view, reason=None) -> bool:
    self = view
    cards = self._live_cards_in_order()
    if cards:
        return self.focus_card(cards[0], reason=reason)
    headers = self._live_headers_in_order()
    return self.focus_card(headers[0], reason=reason) if headers else False

def focus_last_card(view, reason=None) -> bool:
    self = view
    cards = self._live_cards_in_order()
    if cards:
        return self.focus_card(cards[-1], reason=reason)
    headers = self._live_headers_in_order()
    return self.focus_card(headers[-1], reason=reason) if headers else False

def _nav_bands(view) -> list[list[dict]]:
    """Vertical bands of ``{header, cards, cols}`` blocks for Up/Down nav."""
    self = view
    try:
        base_cols = max(1, int(self.grid_columns))
    except Exception:
        base_cols = GRID_COLUMNS
    hdr_entries: list[tuple[int, int, object]] = []
    for hdr in list(getattr(self, "_series_headers", []) or []):
        btn = _header_button(hdr)
        if btn is None:
            continue
        try:
            if not btn.isEnabled():
                continue
            idx = self.items_layout.indexOf(hdr)
        except Exception:
            idx = -1
        if idx < 0:
            continue
        try:
            pos = self.items_layout.getItemPosition(idx)
            r, c = int(pos[0]), int(pos[1])
        except Exception:
            r, c = int(idx), 0
        hdr_entries.append((r, c, btn))
    if not hdr_entries:
        return [[{
            "header": None,
            "cards": self._live_cards_in_order(),
            "cols": base_cols,
        }]]
    card_entries: list[tuple[int, int, object]] = []
    for _path, card in list(getattr(self, "_cards_by_path", {}).items()):
        try:
            if not card.isEnabled():
                continue
            idx = self.items_layout.indexOf(card)
        except Exception:
            idx = -1
        if idx < 0:
            continue
        try:
            pos = self.items_layout.getItemPosition(idx)
            r, c = int(pos[0]), int(pos[1])
        except Exception:
            r, c = int(idx), 0
        card_entries.append((r, c, card))
    st = getattr(self, "_band_state", None)
    if st:
        left_cols, right_cols, sep_col = int(st[0]), int(st[1]), int(st[2])
        band_specs = [(0, max(1, left_cols)), (1, max(1, right_cols))]
    else:
        sep_col = None
        band_specs = [(0, base_cols)]
    bands: list[list[dict]] = []
    for band_id, band_cols in band_specs:
        b_hdrs = [
            (r, c, btn)
            for r, c, btn in hdr_entries
            if (0 if (sep_col is None or c < sep_col) else 1) == band_id
        ]
        b_hdrs.sort(key=lambda t: (t[0], t[1]))
        if not b_hdrs:
            continue
        b_cards = [
            (r, c, card)
            for r, c, card in card_entries
            if (0 if (sep_col is None or c < sep_col) else 1) == band_id
        ]
        b_cards.sort(key=lambda t: (t[0], t[1]))
        blocks = [
            {"header": btn, "row": r, "cards": [], "cols": band_cols}
            for r, _c, btn in b_hdrs
        ]
        for cr, _cc, card in b_cards:
            target_block = blocks[0]
            for blk in blocks:
                if int(blk["row"]) <= cr:
                    target_block = blk
                else:
                    break
            target_block["cards"].append(card)
        bands.append(blocks)
    return bands

def _block_entry(blk):
    """Target entering *blk* from a neighbouring row: header, else 1st card."""
    if blk.get("header") is not None:
        return blk["header"]
    cards = blk.get("cards") or []
    return cards[0] if cards else None

def _block_exit(blk):
    """Target leaving *blk* upward: first card of its last row, else header."""
    cards = blk.get("cards") or []
    if not cards:
        return blk.get("header")
    cols = max(1, int(blk.get("cols") or 1))
    return cards[((len(cards) - 1) // cols) * cols]

def move_focus(view, key) -> bool:
    """Move focus one step for *key*: 2D in grid, Up/Down in list.

    Series headers participate in vertical navigation:
    - Up from the first row of a series block -> that series' header.
    - Down from a header -> the first card of its series (or next header
      when collapsed).
    - Up from the topmost header (or first row with no header) -> yields
      (``False``) so NavigationManager hands off upward.
    - Left/Right on a header yield at row edges without wrapping.

    Side-by-side bands are one vertical strip per band, so Up/Down walk
    on into the adjacent band instead of dead-ending at its edge.
    """
    self = view
    cards = self._live_cards_in_order()
    headers = self._live_headers_in_order()
    if not cards and not headers:
        return False
    cur_card = self.focused_card()
    cur_hdr = self.focused_header() if cur_card is None else None
    if (cur_card is None or cur_card not in cards) and (
        cur_hdr is None or cur_hdr not in headers
    ):
        return self.focus_card(cards[0] if cards else headers[0])

    if cur_hdr is not None:
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.ensure_card_visible(cur_hdr)
            return False
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            bands = self._nav_bands()
            for band_i, band_blocks in enumerate(bands):
                for bi, blk in enumerate(band_blocks):
                    if blk["header"] is not cur_hdr:
                        continue
                    if key == Qt.Key.Key_Down:
                        if blk["cards"]:
                            return self.focus_card(blk["cards"][0])
                        nxt = None
                        if bi + 1 < len(band_blocks):
                            nxt = self._block_entry(band_blocks[bi + 1])
                        elif band_i + 1 < len(bands) and bands[band_i + 1]:
                            nxt = self._block_entry(bands[band_i + 1][0])
                        if nxt is not None:
                            return self.focus_card(nxt)
                        self.ensure_card_visible(cur_hdr)
                        return False
                    # Key_Up
                    prev = band_blocks[bi - 1] if bi > 0 else None
                    if prev is None and band_i > 0 and bands[band_i - 1]:
                        prev = bands[band_i - 1][-1]
                    if prev is not None:
                        tgt = self._block_exit(prev)
                        if tgt is not None:
                            return self.focus_card(tgt)
                    self.ensure_card_visible(cur_hdr)
                    return False
            self.ensure_card_visible(cur_hdr)
            return False
        return False

    try:
        idx = cards.index(cur_card)
    except ValueError:
        return self.focus_card(cards[0])
    if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
        step = -1 if key == Qt.Key.Key_Left else 1
        target = idx + step
        if target < 0 or target >= len(cards):
            self.ensure_card_visible(cur_card)
            return False
        return self.focus_card(cards[target])
    if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
        try:
            cols = int(self.nav_columns_for(_card_drag_path(cur_card)))
        except Exception:
            cols = int(self.grid_columns)
        if cols < 1:
            cols = 1
        bands = self._nav_bands()
        for band_i, band_blocks in enumerate(bands):
            for bi, blk in enumerate(band_blocks):
                blk_cards = blk["cards"]
                if cur_card not in blk_cards:
                    continue
                pos = blk_cards.index(cur_card)
                if key == Qt.Key.Key_Up:
                    if pos >= cols:
                        return self.focus_card(blk_cards[pos - cols])
                    if blk["header"] is not None:
                        return self.focus_card(blk["header"])
                    prev = band_blocks[bi - 1] if bi > 0 else None
                    if prev is None and band_i > 0 and bands[band_i - 1]:
                        prev = bands[band_i - 1][-1]
                    if prev is not None:
                        tgt = self._block_exit(prev)
                        if tgt is not None:
                            return self.focus_card(tgt)
                    self.ensure_card_visible(cur_card)
                    return False
                # Key_Down
                if pos + cols < len(blk_cards):
                    return self.focus_card(blk_cards[pos + cols])
                nxt = None
                if bi + 1 < len(band_blocks):
                    nxt = self._block_entry(band_blocks[bi + 1])
                elif band_i + 1 < len(bands) and bands[band_i + 1]:
                    nxt = self._block_entry(bands[band_i + 1][0])
                if nxt is not None:
                    return self.focus_card(nxt)
                self.ensure_card_visible(cur_card)
                return False
        step = -cols if key == Qt.Key.Key_Up else cols
        target = idx + step
        if target < 0 or target >= len(cards):
            self.ensure_card_visible(cur_card)
            return False
        return self.focus_card(cards[target])
    return False

def _activate_card(view, card) -> bool:
    """Activate *card* via the existing click path (→ Quick Look)."""
    self = view
    path = _card_drag_path(card)
    if path is None:
        return False
    try:
        self._handle_toggle(path)
        return True
    except Exception:
        return False

def _menu_card(view, card) -> bool:
    """Open *card*'s context menu via the existing host callback."""
    self = view
    path = _card_drag_path(card)
    if path is None:
        return False
    try:
        self._handle_context_menu(path)
        return True
    except Exception:
        return False

def select_all_cards(view) -> bool:
    """Ctrl+A → select every pooled item (``use_cases.selection``)."""
    self = view
    try:
        from tabs.image_gallery.use_cases import selection as _selection

        owner = self._drag_owner()
        if owner is None:
            return False
        _selection.select_all(owner)
        return True
    except Exception:
        return False

def forward_key_to_owner(view, event) -> bool:
    """Route *event* to the owner widget's triage key handler.

    Space/Delete remove-from-view and Escape live in
    ``triage_ui.handle_key`` (reached through ``ImageGalleryWidget
    .keyPressEvent``); forwarding keeps one implementation of those
    semantics instead of a second copy here.
    """
    self = view
    owner = getattr(self, "_gallery_widget", None)
    if owner is None:
        return False
    try:
        owner.keyPressEvent(event)
        return True
    except Exception:
        return False

def handle_navigation_key(view, event) -> bool:
    """Consume navigation keys (arrows / Home / End / Menu) for the grid.

    Called from ``GalleryGridView.keyPressEvent`` and from the owner
    widget's ``keyPressEvent`` (focus on the widget but not yet a card)
    and from ``_CardKeyFilter`` (card focused). Returns True when the
    event was handled.
    """
    self = view
    try:
        key = event.key()
    except Exception:
        return False
    cards = self._live_cards_in_order()
    headers = self._live_headers_in_order()
    if not cards and not headers:
        return False
    # Two branches on purpose (not one four-key tuple): the grid maps all
    # four arrows, but the arrow-redirection dogma forbids grouping
    # Down+Right / Up+Left in a single test expression.
    if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
        return bool(self.move_focus(key))
    if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
        return bool(self.move_focus(key))
    if key == Qt.Key.Key_Home:
        return bool(self.focus_first_card())
    if key == Qt.Key.Key_End:
        return bool(self.focus_last_card())
    if key == Qt.Key.Key_Menu:
        card = self.focused_card() or (cards[0] if cards else None)
        return bool(self._menu_card(card)) if card is not None else False
    return False

def _focus_snapshot(view):
    """(path/header-id, order index) of the focused card or header."""
    self = view
    card = self.focused_card()
    if card is not None:
        path = _card_drag_path(card)
        try:
            index = self._live_cards_in_order().index(card)
        except Exception:
            index = None
        return (str(path) if path is not None else None, index)
    hdr = self.focused_header()
    if hdr is not None:
        try:
            name = str(hdr.objectName() or "")
        except Exception:
            name = ""
        try:
            index = self._live_headers_in_order().index(hdr)
        except Exception:
            index = None
        return (f"header:{name}" if name else None, index)
    return (None, None)

def _restore_focus(view, snapshot) -> bool:
    """Re-focus a :meth:`_focus_snapshot` after a rebuild/recycle.

    Never grants focus when the snapshot was empty (focus was not on a
    card or header) — a rebuild driven by the toolbar filter must not
    steal focus.
    """
    self = view
    try:
        path, index = snapshot if snapshot else (None, None)
    except Exception:
        path, index = None, None
    if isinstance(path, str) and path.startswith("header:"):
        want_name = path[len("header:"):]
        headers = self._live_headers_in_order()
        for btn in headers:
            try:
                if str(btn.objectName() or "") == want_name and btn.isVisible() and btn.isEnabled():
                    return bool(self.focus_card(btn))
            except Exception:
                continue
        if headers and index is not None:
            try:
                target = max(0, min(int(index), len(headers) - 1))
            except Exception:
                target = 0
            return bool(self.focus_card(headers[target]))
        cards = self._live_cards_in_order()
        return bool(self.focus_card(cards[0])) if cards else False
    if path:
        card = self._cards_by_path.get(str(path))
        if card is not None:
            try:
                if card.isVisible() and card.isEnabled():
                    return bool(self.focus_card(card))
            except Exception:
                pass
    if index is None:
        return False
    cards = self._live_cards_in_order()
    if not cards:
        headers = self._live_headers_in_order()
        return bool(self.focus_card(headers[0])) if headers else False
    try:
        target = max(0, min(int(index), len(cards) - 1))
    except Exception:
        target = 0
    return bool(self.focus_card(cards[target]))

def key_press_event(view, event) -> bool:
    """Grid-level key press; True when consumed."""
    self = view
    try:
        if self.handle_navigation_key(event):
            event.accept()
            return True
    except Exception:
        pass
    return False
