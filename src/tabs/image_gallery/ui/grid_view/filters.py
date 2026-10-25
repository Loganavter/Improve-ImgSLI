"""Card press-drag / keyboard event filters (grid_view package, plan C1)."""

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
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _card_drag_path(card):
    """Resolve ``_card_drag_path`` from the ``drag_source`` sibling.

    Lazy: ``drag_source`` imports ``filters`` at module load, so a top-level
    import here would be circular. Keeps the same name/signature.
    """
    from tabs.image_gallery.ui.grid_view.drag_source import _card_drag_path as _fn

    return _fn(card)


class _CardPressDragFilter(QObject):
    """Card press-move → QDrag kickoff (Wave A drag source).

    Installed on each pooled card (see ``GalleryGridView._ensure_card_drag``).
    Observes only — returns False except for the release that ends a completed
    drag (swallowed so no click activates after a drop). Marquee is
    unaffected: it starts on empty-host presses only.
    """

    def __init__(self, card, view) -> None:  # type: ignore[no-untyped-def]
        super().__init__(card)
        self._card = card
        self._view = view
        self._dragged = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._card:
            return False
        try:
            etype = event.type()
        except Exception:
            return False
        if etype == QEvent.Type.MouseButtonPress:
            try:
                if event.button() == Qt.MouseButton.LeftButton:
                    path = _card_drag_path(self._card)
                    if path is not None:
                        self._dragged = False
                        self._view.note_card_press(path, event.globalPosition().toPoint())
            except Exception:
                pass
        elif etype == QEvent.Type.MouseMove:
            try:
                if (
                    not self._dragged
                    and bool(event.buttons() & Qt.MouseButton.LeftButton)
                    and self._view.maybe_start_card_drag(self._card, event.globalPosition().toPoint())
                ):
                    self._dragged = True
            except Exception:
                pass
        elif etype == QEvent.Type.MouseButtonRelease:
            try:
                self._view.clear_card_press()
            except Exception:
                pass
            if self._dragged:
                self._dragged = False
                return True
        return False

class _CardKeyFilter(QObject):
    """Card-focused keyboard policy (installed on every pooled card).

    Mirrors the session-picker card grid (``tabs.session_picker.recent
    .items_view`` — ``navigate_focus`` / ``activate_focused_card`` /
    ``_ensure_index_visible``): arrows/Home/End/Menu drive focus inside the
    grid and Return activates the focused card. This filter runs *before*
    the toolkit ``Button``'s own ``keyPressEvent``, which would otherwise
    treat Space/Return as an activation click — Space must stay
    "remove from view" for the gallery, so it is routed back to the owner
    widget's triage handler instead (``ui/card.py`` card vs ``triage_ui``).

    Pool-safe: parented to *card* (Qt keeps it alive), idempotently marked by
    ``GalleryGridView._ensure_card_keys``.
    """

    def __init__(self, card, view) -> None:  # type: ignore[no-untyped-def]
        super().__init__(card)
        self._card = card
        self._view = view

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is not self._card:
            return False
        try:
            if event.type() != QEvent.Type.KeyPress:
                return False
        except Exception:
            return False
        try:
            key = event.key()
            mods = event.modifiers()
        except Exception:
            return False
        # Arrows / Home / End / context-menu key → grid focus navigation.
        try:
            if self._view.handle_navigation_key(event):
                return True
        except Exception:
            pass
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            try:
                if self._view._activate_card(self._card):
                    return True
            except Exception:
                pass
            return False
        try:
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        except Exception:
            ctrl = False
        if ctrl and key == Qt.Key.Key_A:
            try:
                if self._view.select_all_cards():
                    return True
            except Exception:
                pass
            return False
        if key in (
            Qt.Key.Key_Space,
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Escape,
        ):
            # Preserve the gallery's remove-from-view / close semantics: the
            # Button would otherwise activate the card on Space.
            try:
                return bool(self._view.forward_key_to_owner(event))
            except Exception:
                return False
        return False
