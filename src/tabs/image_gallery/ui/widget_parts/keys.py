"""Keyboard handling + controller attach for the gallery widget (plan Part B, Wave 3).

Bodies extracted from ``ImageGalleryWidget`` per ``CODE_PATTERNS.md``
(thin owner + functions-taking-owner); the class keeps the Qt-required
``keyPressEvent`` name (delegating to ``key_press_event`` here) plus the
same-named ``attach_controller`` / ``_owner_for_triage`` methods, so call
sites and tests do not move. Fail-open like the surrounding widget chrome.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def attach_controller(owner, controller) -> None:
    """Attach the owning ``GalleryController`` (first wins, fail-open).

    Called once by ``ImageGalleryTab.create_page`` (G1 side of the
    gallery-contracts seam). A second call is a protocol violation:
    logged at debug and ignored — last wins is forbidden.
    """
    try:
        if owner._attached_controller is not None:
            logger.debug(
                "ImageGalleryWidget.attach_controller: already attached, ignoring double-attach"
            )
            return
    except AttributeError:
        pass
    owner._attached_controller = controller
    # Refresh the zone-drop binding with the now-known controller.
    try:
        from tabs.image_gallery.ui import drag_drop as _drag_drop

        _drag_drop.install_zone_drop_forwarding(owner, controller)
    except Exception:
        pass


def _owner_for_triage(owner):
    """Return the attached controller, or self when unattached (fail-open).

    Storeless unit tests construct the widget bare (no tab wiring), so
    ``None`` attachment falls back to the widget itself, which carries
    ``state``-compatible reads. No other fallback chain — no attribute
    scan, no window walk (G2 gallery contract).
    """
    try:
        ctrl = owner._attached_controller
    except AttributeError:
        ctrl = None
    if ctrl is not None:
        return ctrl
    return owner


def key_press_event(owner, event) -> None:
    from tabs.image_gallery.use_cases import triage_ui

    # While the toolbar filter has focus, arrows/Home/End belong to the
    # text field — keep the triage_ui typing guard intact (it also runs
    # inside handle_key, but navigation would steal the keys first).
    try:
        from PySide6.QtWidgets import QApplication

        fw = QApplication.focusWidget()
        filter_edit = getattr(owner, "_filter_edit", None)
        if fw is not None and fw is filter_edit and event.key() != Qt.Key.Key_Escape:
            return triage_ui.handle_key(owner, event)
    except Exception:
        pass
    # Card-grid navigation (arrows / Home / End / Menu) is owned by the
    # grid view — mirrors session_picker/recent/items_view. When no card
    # holds focus yet, an arrow bootstraps onto the first card. Everything
    # else (Space/Delete remove, Enter compare, Esc, B) stays in triage_ui.
    try:
        if owner._grid_view.handle_navigation_key(event):
            event.accept()
            return
    except Exception:
        pass
    return triage_ui.handle_key(owner, event)
