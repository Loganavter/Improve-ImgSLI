"""ScrollValueButton — app-level recreation of the built-in scroll/value
counter that sli-ui-toolkit 0.2.16 removed from ``Button``.

The toolkit no longer knows about ``scrollable=``/``valueChanged``/``get_value``/
``set_value`` at all: it only exposes generic extension points
(``ButtonCapability.handle_wheel_event`` and custom ``Layer``s via
``Button(layers=...)``). This module composes those primitives back into the
old surface so the rest of the app (which still calls ``get_value()``,
``set_value()``, ``valueChanged``, ``get_saved_value()``/``set_saved_value()``,
``restore_saved_value()``, ``underline_visible_when=``,
``checked_background_visible_when=``) keeps working unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any, Callable

from PySide6.QtCore import QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPixmap, QWheelEvent
from sli_ui_toolkit.ui.widgets.buttons.capabilities import ButtonCapability
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.layers.background import BackgroundLayer
from sli_ui_toolkit.ui.widgets.buttons.layers.content import ContentLayer
from sli_ui_toolkit.ui.widgets.buttons.painter import default_layers
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style
from sli_ui_toolkit.widgets import Button

from shared_toolkit.ui.overlay_layer import get_overlay_layer

logger = logging.getLogger("ImproveImgSLI")

_SCROLLING_DEBOUNCE_MS = 400
_VALUE_LABEL_HEIGHT = 11
# Reserved strip at the very bottom, below the value label, left clear for
# UnderlineLayer's line so it never overlaps the label text.
_UNDERLINE_CLEARANCE_PX = 3
# Visual gap between the shrunk icon and the value label below it, so they
# don't visually touch even though their regions are adjacent.
_ICON_LABEL_GAP_PX = 4


class _ScrollValueCapability(ButtonCapability):
    def __init__(self, owner: "ScrollValueButton") -> None:
        super().__init__()
        self._owner = owner
        self._end_timer: QTimer | None = None

    def attach(self, button, region_id: str | None = None) -> None:
        super().attach(button, region_id=region_id)

    def detach(self, button) -> None:
        if self._end_timer is not None:
            self._end_timer.stop()
            self._end_timer.deleteLater()
            self._end_timer = None

    def _on_scroll_end(self) -> None:
        owner = self._owner
        owner._is_scrolling = False
        owner._hide_value_popup()
        owner.update()

    def handle_wheel_event(self, event: QWheelEvent) -> bool:
        delta = event.angleDelta().y()
        logger.debug(
            "[scroll-debug] handle_wheel_event owner=%s delta=%s value=%s",
            self._owner.objectName() or type(self._owner).__name__,
            delta,
            self._owner._scroll_value,
        )
        if delta == 0:
            return False
        owner = self._owner
        step = 1 if delta > 0 else -1
        new_value = max(owner._scroll_min, min(owner._scroll_max, owner._scroll_value + step))
        owner._is_scrolling = True
        if self._end_timer is None:
            self._end_timer = QTimer(owner)
            self._end_timer.setSingleShot(True)
            self._end_timer.timeout.connect(self._on_scroll_end)
        self._end_timer.start(_SCROLLING_DEBOUNCE_MS)
        if new_value != owner._scroll_value:
            owner._scroll_value = new_value
            owner.valueChanged.emit(new_value)
        owner.update()
        owner._show_value_popup()
        event.accept()
        return True


class _ConditionalCheckedBackgroundLayer(Layer):
    """Paints BackgroundLayer as if CHECKED were unset when the predicate says so.

    Some buttons pass ``toggle=True`` purely as bookkeeping for the
    scroll-boundary "0 = off" behavior and must never show the checked-state
    background capsule for it.
    """

    def __init__(self, owner: "ScrollValueButton", predicate: Callable[["ScrollValueButton"], bool]) -> None:
        self._owner = owner
        self._predicate = predicate
        self._inner = BackgroundLayer()

    def draw(self, ctx, tm) -> None:
        if not self._predicate(self._owner):
            if ctx.region_states is not None:
                ctx = replace(ctx, region_states=ctx.region_states - {ButtonState.CHECKED})
            else:
                ctx = replace(ctx, states=ctx.states - {ButtonState.CHECKED})
        self._inner.draw(ctx, tm)


class _ShrunkContentLayer(Layer):
    """Wraps ``ContentLayer``. While hovered, the icon renders in a shrunk
    top region so the scroll-value label has its own space below instead of
    overlapping it. With no hover, the reserved region is dropped and the
    icon draws over the full button rect as usual.
    """

    def __init__(self, owner: "ScrollValueButton") -> None:
        self._owner = owner
        self._inner = ContentLayer()

    def applies(self, ctx) -> bool:
        return self._inner.applies(ctx)

    def draw(self, ctx, tm) -> None:
        if not (self._owner._is_scrolling or ButtonState.HOVERED in ctx.states):
            self._inner.draw(ctx, tm)
            return
        rect = ctx.effective_rect
        shrunk_height = max(0.0, rect.height() - _VALUE_LABEL_HEIGHT - _UNDERLINE_CLEARANCE_PX)
        shrunk = QRectF(rect.x(), rect.y(), rect.width(), shrunk_height)
        # The icon is drawn at a fixed pixel size, not scaled to its region, so
        # a shrunk region exactly as tall as the icon leaves zero breathing
        # room between icon and value label below it. Shrink the icon itself
        # a bit so it visibly floats inside the region instead of touching it.
        icon_size = min(ctx.effective_icon_size_px, max(0, int(shrunk_height) - _ICON_LABEL_GAP_PX))
        self._inner.draw(
            replace(ctx, region_rect=shrunk, region_icon_size_px=icon_size), tm
        )


class _ValueLabelLayer(Layer):
    """Draws the current value at the bottom of the button while hovered.

    Suppressed during an active scroll: the scroll popup (above the button)
    takes over as the value indicator in that case instead.
    """

    scope = "widget"

    def __init__(self, owner: "ScrollValueButton") -> None:
        self._owner = owner

    def applies(self, ctx) -> bool:
        return self._owner._is_scrolling or ButtonState.HOVERED in ctx.states

    def draw(self, ctx, tm) -> None:
        widget = ctx.widget
        p = ctx.painter
        owner = self._owner
        label_rect = QRect(
            0,
            widget.height() - _VALUE_LABEL_HEIGHT - _UNDERLINE_CLEARANCE_PX,
            widget.width(),
            _VALUE_LABEL_HEIGHT,
        )
        if owner._scroll_value == 0:
            pixmap = owner._zero_icon_pixmap(_VALUE_LABEL_HEIGHT)
            if pixmap is not None:
                x = label_rect.center().x() - pixmap.width() // 2
                p.drawPixmap(x, label_rect.top(), pixmap)
                return
        style = read_widget_style(widget)
        text_color = QColor(style.foreground_color or tm.get_color("dialog.text"))
        font = QFont()
        font.setBold(True)
        font.setPixelSize(9)
        p.setFont(font)
        p.setPen(text_color)
        p.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            str(owner._scroll_value),
        )


class ScrollValueButton(Button):
    """Button with a wheel-driven clamped int value (old ``scrollable=`` recipe)."""

    valueChanged = Signal(int)

    def __init__(
        self,
        icon: Any = None,
        *,
        scrollable: tuple[int, int],
        start: int = 0,
        underline_visible_when: Callable[["ScrollValueButton"], bool] | None = None,
        checked_background_visible_when: Callable[["ScrollValueButton"], bool] | None = None,
        zero_icon: Any = None,
        layers: list[Layer] | None = None,
        **kwargs: Any,
    ) -> None:
        self._scroll_min, self._scroll_max = scrollable
        self._scroll_value = max(self._scroll_min, min(self._scroll_max, start))
        self._saved_value: int | None = None
        self._underline_visible_when = underline_visible_when
        self._zero_icon = zero_icon
        self._is_scrolling = False
        self._value_popup_key = f"scroll_value:{id(self)}"

        if layers is None:
            layers = default_layers()
        if checked_background_visible_when is not None:
            layers = [
                _ConditionalCheckedBackgroundLayer(self, checked_background_visible_when)
                if isinstance(layer, BackgroundLayer)
                else layer
                for layer in layers
            ]
        layers = [
            _ShrunkContentLayer(self) if isinstance(layer, ContentLayer) else layer
            for layer in layers
        ]
        layers = [*layers, _ValueLabelLayer(self)]

        super().__init__(icon, layers=layers, **kwargs)
        self.attach_capability(_ScrollValueCapability(self))
        self.valueChanged.connect(self._sync_underline_visibility)
        self._sync_underline_visibility()

    def _sync_underline_visibility(self, *_args: Any) -> None:
        if self._underline_visible_when is not None:
            self.setShowUnderline(bool(self._underline_visible_when(self)))

    def setUnderlineColor(self, *args: Any, **kwargs: Any) -> None:
        # set_value() only emits valueChanged (and thus re-runs
        # _sync_underline_visibility) when the value actually changes. When a
        # toolbar sync sets the color while the value already matches the
        # target, that signal never fires again, leaving show_underline
        # stuck at whatever it was resolved to at construction time (value
        # was still 0 then, so underline_visible_when was False). Re-check
        # visibility on every color update so it can't get stuck.
        super().setUnderlineColor(*args, **kwargs)
        self._sync_underline_visibility()

    def _zero_icon_pixmap(self, size: int) -> QPixmap | None:
        if self._zero_icon is None:
            return None
        from ui.icon_manager import get_app_icon

        return get_app_icon(self._zero_icon).pixmap(size, size)

    def _show_value_popup(self, timeout_ms: int = 0) -> None:
        overlay_layer = get_overlay_layer(self)
        if overlay_layer is None:
            return
        pixmap = self._zero_icon_pixmap(16) if self._scroll_value == 0 else None
        overlay_layer.show_popup(
            self._value_popup_key,
            self,
            text="" if pixmap is not None else str(self._scroll_value),
            pixmap=pixmap,
            position="top",
            offset=6,
            timeout_ms=timeout_ms,
        )

    def _hide_value_popup(self) -> None:
        overlay_layer = get_overlay_layer(self)
        if overlay_layer is None:
            return
        overlay_layer.hide_popup(self._value_popup_key)

    def get_value(self) -> int:
        return self._scroll_value

    def set_value(self, value: int, emit: bool = True) -> None:
        clamped = max(self._scroll_min, min(self._scroll_max, int(value)))
        if clamped == self._scroll_value:
            return
        self._scroll_value = clamped
        if emit:
            self.valueChanged.emit(clamped)
        self.update()

    def setRange(self, min_value: int, max_value: int) -> None:
        self._scroll_min, self._scroll_max = min_value, max_value
        self.set_value(self._scroll_value, emit=False)

    def get_saved_value(self) -> int | None:
        return self._saved_value

    def set_saved_value(self, value: int | None) -> None:
        self._saved_value = value

    def restore_saved_value(self) -> int | None:
        value = self._saved_value
        self._saved_value = None
        return value
