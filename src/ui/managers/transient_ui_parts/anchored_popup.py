from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize

from sli_ui_toolkit.managers import DelayedActionTimer
from shared_toolkit.ui.overlay_layer import get_overlay_layer

class AnchoredPopupBubbleController:
    def __init__(
        self,
        *,
        host,
        popup_key: str,
        auto_hide_delay_ms: int,
        on_before_show: Callable[[], None] | None = None,
        on_hidden: Callable[[], None] | None = None,
        should_keep_open: Callable[[], bool] | None = None,
    ):
        self.host = host
        self.popup_key = popup_key
        self.auto_hide_delay_ms = int(auto_hide_delay_ms)
        self.on_before_show = on_before_show
        self.on_hidden = on_hidden
        self.should_keep_open = should_keep_open
        self._anchor = None
        self._auto_hide_timer = DelayedActionTimer(self._on_timeout, parent=host)

    def is_open(self) -> bool:
        return bool(getattr(self.host, "_magn_instances_popup_open", False))

    def show(
        self,
        *,
        anchor_widget,
        text: str = "",
        pixmap=None,
        size: QSize,
        position: str = "top",
        offset: int = 6,
    ) -> bool:
        overlay_layer = get_overlay_layer(anchor_widget)
        if overlay_layer is None:
            return False
        if self.on_before_show is not None:
            self.on_before_show()
        self._anchor = anchor_widget
        overlay_layer.show_popup(
            self.popup_key,
            anchor_widget,
            text=text,
            pixmap=pixmap,
            size=size,
            position=position,
            offset=offset,
            timeout_ms=0,
        )
        self.restart_auto_hide()
        return True

    def restart_auto_hide(self) -> None:
        self._auto_hide_timer.stop()
        self._auto_hide_timer.start(self.auto_hide_delay_ms)

    def _on_timeout(self) -> None:
        if self.should_keep_open is not None and self.should_keep_open():
            self.restart_auto_hide()
            return
        self.hide()

    def hide(self) -> None:
        overlay_layer = get_overlay_layer(self._anchor)
        if overlay_layer is not None:
            overlay_layer.hide_popup(self.popup_key)
        self._auto_hide_timer.stop()
        self._anchor = None
        if self.on_hidden is not None:
            self.on_hidden()
