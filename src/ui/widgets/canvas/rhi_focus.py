"""Keep keyboard focus off QRhiWidget hosts on Wayland/Vulkan.

Focused ``QRhiWidget`` + compositor deactivation (``ApplicationInactive``)
can restack the Vulkan subsurface when a transient opens — MC shows this as a
zoom “nudge” while store zoom/pan and the color buffer stay unchanged. IC
usually keeps focus on the tab shell (``ImageCompareWidget``) instead.

Parking moves focus to the nearest non-RHI ancestor that accepts focus.
``MultiCompareWidget.keyPressEvent`` already forwards keys to the canvas.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QRhiWidget, QWidget

_filter: _ParkQrhiFocusFilter | None = None


def park_keyboard_focus_off_qrhi(hint: QWidget | None = None) -> bool:
    """If a ``QRhiWidget`` holds focus, move it to a non-RHI ancestor.

    Returns True when focus was moved or cleared.
    """
    app = QApplication.instance()
    focused = hint if isinstance(hint, QRhiWidget) and hint.hasFocus() else None
    if focused is None and app is not None:
        current = app.focusWidget()
        if isinstance(current, QRhiWidget):
            focused = current
    if focused is None:
        return False

    park = focused.parentWidget()
    while park is not None:
        if isinstance(park, QRhiWidget):
            park = park.parentWidget()
            continue
        if park.focusPolicy() != Qt.FocusPolicy.NoFocus:
            park.setFocus(Qt.FocusReason.OtherFocusReason)
            return True
        park = park.parentWidget()
    focused.clearFocus()
    return True


class _ParkQrhiFocusFilter(QObject):
    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.FocusIn and isinstance(watched, QRhiWidget):
            park_keyboard_focus_off_qrhi(watched)
        return False


def install_qrhi_focus_parking(widget: QRhiWidget) -> None:
    """Install a process-shared FocusIn filter that parks focus off ``widget``."""
    global _filter
    if _filter is None:
        _filter = _ParkQrhiFocusFilter()
    widget.installEventFilter(_filter)
