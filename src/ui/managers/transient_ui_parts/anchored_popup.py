from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint, QRect, QSize

from sli_ui_toolkit.managers import DelayedActionTimer
from shared_toolkit.ui.overlay_layer import (
    content_bounds,
    get_content_overlay_layer,
    get_overlay_layer,
)

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
        self._clamp_to_content_below_strip(overlay_layer, anchor_widget)
        return True

    def _clamp_to_content_below_strip(self, overlay_layer, anchor_widget) -> None:
        """Clamp a content-anchored popup below the AdaptiveTabStrip band.

        CLAMP ONLY, NO REPARENT: the popup keeps its window-layer parent and
        legacy placement; when the anchor lives in the below-strip content
        subtree we only pull the shown global geometry out of the strip
        band (intersect against the content global rect). Anchors in global
        chrome (menus, dialogs, CSD, startup with no content host yet) keep
        byte-identical legacy geometry. Fail-open everywhere.
        """
        try:
            content_layer = get_content_overlay_layer(anchor_widget)
        except Exception:
            return
        if content_layer is None:
            return
        try:
            is_content = bool(getattr(content_layer, "_is_content_layer", False))
        except Exception:
            return
        if not is_content:
            return  # global chrome / startup fallback: legacy behavior
        try:
            popups = getattr(overlay_layer, "_value_popups", None)
            popup = popups.get(self.popup_key) if popups else None
            if popup is None:
                return
            geom = popup.geometry()
            if not geom.isValid():
                return
            host = content_layer.host
            bounds = content_bounds(anchor_widget)
            if bounds.isNull() or bounds.width() <= 0 or bounds.height() <= 0:
                return
            content_top_left = host.mapToGlobal(QPoint(0, 0))
            content_rect = QRect(content_top_left, bounds.size())
            strip_rect = self._strip_global_rect(anchor_widget)
            clamped = self._clamp_global_to_content(geom, content_rect)
            if strip_rect is not None and clamped.intersects(strip_rect):
                # Content starts below the strip, so pinning above the
                # strip band's bottom edge restores disjointness.
                clamped.moveTop(max(clamped.top(), strip_rect.bottom() + 1))
                clamped = self._clamp_global_to_content(clamped, content_rect)
            if clamped != geom:
                popup.setGeometry(clamped)
        except Exception:
            return

    @staticmethod
    def _strip_global_rect(anchor_widget):
        """workspace_tabs mapped to global; None when unresolvable (doubles)."""
        try:
            window = anchor_widget.window()
        except Exception:
            return None
        try:
            tabs = getattr(getattr(window, "ui", None), "workspace_tabs", None)
            if tabs is None:
                tabs = getattr(window, "workspace_tabs", None)
            if tabs is None:
                return None
            return QRect(tabs.mapToGlobal(QPoint(0, 0)), tabs.size())
        except Exception:
            return None

    @staticmethod
    def _clamp_global_to_content(geom: QRect, content_rect: QRect) -> QRect:
        width = min(geom.width(), content_rect.width())
        height = min(geom.height(), content_rect.height())
        x = max(content_rect.left(), min(geom.x(), content_rect.right() - width + 1))
        y = max(content_rect.top(), min(geom.y(), content_rect.bottom() - height + 1))
        return QRect(x, y, width, height)

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
