"""NavigationManager section for the gallery card grid (grid_view package, plan C1)."""

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

class GalleryGridNavSection:
    """``NavigationSection`` for the gallery card grid (NavigationManager).

    Registered by ``ImageGalleryTab`` under the grid view so the app-wide
    ``NavigationManager`` owns arrow consumption on cards and can trial-dispatch
    an edge press to the neighbouring section (the toolbar above the grid → an
    Up at the first row hands off; Down from the toolbar enters the grid).
    Left/Right are opted into here (``extra_keys``) because the grid is a real
    2D layout: the manager routes all four arrows to :meth:`navigate`, and a
    row-edge press declines (``False``) instead of being remapped.

    ``owns`` claims only live cards — never the toolbar, series headers or the
    host — so the toolbar rows section and this one stay disjoint.
    """

    def __init__(self, view: "GalleryGridView") -> None:
        self._view = view

    @property
    def extra_keys(self) -> frozenset:
        # Grid layout legitimately maps all four arrows spatially.
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})

    def owns(self, widget) -> bool:
        try:
            if widget in set(self._view._cards_by_path.values()):
                return True
            # The empty grid area below the cards (grid host / scroll viewport,
            # incl. its viewport): a click there realigns the ring onto the
            # scroll area, which owns no keys — arrows died "reveal-only" and
            # nothing was reachable by keyboard. Claiming the scroll subtree
            # routes arrows to the grid so a key reaches the nearest card.
            scroll = getattr(self._view, "scroll_area", None)
            if scroll is not None and (
                widget is scroll
                or bool(getattr(scroll, "isAncestorOf", lambda _w: False)(widget))
            ):
                return True
            return False
        except Exception:
            return False

    def navigate(self, key: int, widget) -> bool:
        try:
            return bool(self._view.move_focus(key))
        except Exception:
            return False

    def focus_first(self, ref_x=None, *, reason):
        try:
            return bool(self._view.focus_first_card(reason=reason))
        except Exception:
            return False

    def focus_last(self, ref_x=None, *, reason):
        try:
            return bool(self._view.focus_last_card(reason=reason))
        except Exception:
            return False
