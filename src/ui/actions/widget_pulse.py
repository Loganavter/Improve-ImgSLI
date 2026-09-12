"""In-window pulse highlight for ActionTarget widgets (Find Action reveal)."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager

from ui.theming import resolve_theme_color

# Thin toolkit controls (sliders) need a larger hit-box so the ring is readable.
_MIN_PULSE_HEIGHT = 28
_MIN_PULSE_WIDTH = 40
_PULSE_PAD = 4
# Always sit slightly outside the widget so the ring is not lost on
# accent-filled chrome (Settings / Help sidebar selected row).
_PULSE_OUTSET = 3


def _contrast_for_accent(accent: QColor) -> QColor:
    """White/black halo so an accent ring stays visible on accent fills."""
    lum = (299 * accent.red() + 587 * accent.green() + 114 * accent.blue()) // 1000
    return QColor(255, 255, 255) if lum < 160 else QColor(0, 0, 0)


class _PulseOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("ActionPulseOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._target_rect = QRect()
        self._alpha = 220
        self.hide()

    def set_target(self, rect: QRect, *, alpha: int) -> None:
        self._target_rect = QRect(rect)
        self._alpha = max(0, min(255, int(alpha)))
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ARG002 — Qt API
        if self._target_rect.isNull() or not self._target_rect.isValid():
            return
        try:
            accent = resolve_theme_color(ThemeManager.get_instance(), "accent")
        except Exception:
            accent = QColor("#3d8bfd")
        ring = self._target_rect.adjusted(1, 1, -2, -2)
        halo = _contrast_for_accent(accent)
        halo.setAlpha(min(255, self._alpha))
        color = QColor(accent)
        color.setAlpha(self._alpha)
        fill = QColor(accent)
        fill.setAlpha(max(0, self._alpha // 5))
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # Outer contrast stroke first — readable on selected sidebar rows.
            painter.setPen(QPen(halo, 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(ring, 6, 6)
            painter.setPen(QPen(color, 2))
            painter.setBrush(fill)
            painter.drawRoundedRect(ring.adjusted(2, 2, -2, -2), 5, 5)
        finally:
            painter.end()


_ACTIVE: _PulseOverlay | None = None


def _cpp_alive(obj) -> bool:
    if obj is None:
        return False
    try:
        import shiboken6

        return bool(shiboken6.isValid(obj))
    except Exception:
        return True


def _dispose_overlay(overlay: _PulseOverlay | None) -> None:
    global _ACTIVE
    if overlay is None:
        return
    if _ACTIVE is overlay:
        _ACTIVE = None
    if not _cpp_alive(overlay):
        return
    try:
        overlay.hide()
    except RuntimeError:
        pass
    try:
        overlay.deleteLater()
    except RuntimeError:
        pass


def _flyout_ancestor(widget: QWidget) -> QWidget | None:
    """Nearest BaseFlyout-like ancestor (has ``flyout_group``)."""
    node = widget
    while node is not None:
        if getattr(type(node), "flyout_group", None):
            return node
        node = node.parentWidget()
    return None


def _overlay_parent_for(target: QWidget, host: QWidget | None) -> QWidget:
    """Prefer the flyout itself so the ring paints above in-window flyout chrome."""
    if host is not None:
        return host
    flyout = _flyout_ancestor(target)
    if flyout is not None:
        return flyout
    window = target.window()
    return window if window is not None else target


def _pulse_rect(target: QWidget, origin: QWidget) -> QRect:
    top_left = target.mapTo(origin, QPoint(0, 0))
    rect = target.rect().translated(top_left)
    grow_x = _PULSE_OUTSET
    grow_y = _PULSE_OUTSET
    if rect.width() < _MIN_PULSE_WIDTH or rect.height() < _MIN_PULSE_HEIGHT:
        grow_x = max(
            grow_x, _PULSE_PAD + max(0, (_MIN_PULSE_WIDTH - rect.width() + 1) // 2)
        )
        grow_y = max(
            grow_y, _PULSE_PAD + max(0, (_MIN_PULSE_HEIGHT - rect.height() + 1) // 2)
        )
    return rect.adjusted(-grow_x, -grow_y, grow_x, grow_y)


def pulse_widget(
    target: object,
    *,
    host: QWidget | None = None,
    duration_ms: int = 1400,
    pulses: int = 3,
    _retry: int = 0,
) -> None:
    """Blink an accent ring around ``target``.

    When ``target`` lives inside a toolkit flyout, the overlay is parented to
    that flyout so stacking stays above sliders/switches. Thin targets are
    padded so the ring stays readable.
    """
    global _ACTIVE
    if not isinstance(target, QWidget):
        return
    if not _cpp_alive(target):
        return
    if not target.isVisible():
        # Flyout / edit-row chrome may still be settling after ensure_visible.
        if _retry < 4:
            QTimer.singleShot(
                50,
                lambda t=target, h=host, d=duration_ms, p=pulses, r=_retry: pulse_widget(
                    t, host=h, duration_ms=d, pulses=p, _retry=r + 1
                ),
            )
        return

    window = _overlay_parent_for(target, host)
    if window is None or not _cpp_alive(window):
        return

    if _ACTIVE is not None:
        _dispose_overlay(_ACTIVE)

    overlay = _PulseOverlay(window)
    rect = _pulse_rect(target, window)
    overlay.set_target(rect, alpha=230)
    _ACTIVE = overlay

    steps = max(1, pulses * 2)
    interval = max(40, duration_ms // steps)
    state = {"step": 0}

    def _tick() -> None:
        global _ACTIVE
        if _ACTIVE is not overlay:
            return
        if not _cpp_alive(overlay):
            if _ACTIVE is overlay:
                _ACTIVE = None
            return
        state["step"] += 1
        if state["step"] >= steps:
            _dispose_overlay(overlay)
            return
        # Odd steps fade out, even steps peak.
        alpha = 70 if state["step"] % 2 else 230
        if _cpp_alive(target) and target.isVisible() and _cpp_alive(window):
            try:
                overlay.set_target(_pulse_rect(target, window), alpha=alpha)
                return
            except RuntimeError:
                _dispose_overlay(overlay)
                return
        try:
            overlay.set_target(rect, alpha=alpha)
        except RuntimeError:
            _dispose_overlay(overlay)

    for i in range(1, steps + 1):
        QTimer.singleShot(interval * i, _tick)
