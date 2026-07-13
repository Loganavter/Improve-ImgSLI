from __future__ import annotations

import logging
import os

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPalette, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QRhiWidget

from core.state_management.interaction_actions import SetResizeInProgressAction

logger = logging.getLogger("ImproveImgSLI")

_RESIZE_SHIELD_ATTR = "_imgsli_resize_shield"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def _resize_debug_enabled() -> bool:
    return _env_flag("IMGSLI_RESIZE_DEBUG") or _env_flag("IMGSLI_RESIZE_DEBUG_VISUAL")


def _resize_visual_debug_enabled() -> bool:
    return _env_flag("IMGSLI_RESIZE_DEBUG_VISUAL")


def _resize_shield_enabled() -> bool:
    return _env_flag("IMGSLI_RESIZE_SHIELD")


def _resize_debug(message: str, *args, exc_info=False) -> None:
    if _resize_debug_enabled():
        logger.debug("[resize-debug] " + message, *args, exc_info=exc_info)


def _rhi_debug_id(rhi) -> str:
    name = rhi.objectName() or "<unnamed>"
    return f"{type(rhi).__name__}@{id(rhi):x} objectName={name}"


def _rhi_debug_state(rhi) -> str:
    fixed = rhi.fixedColorBufferSize()
    parent = rhi.parentWidget()
    parent_name = type(parent).__name__ if parent is not None else "None"
    return (
        f"size={rhi.size().width()}x{rhi.size().height()} "
        f"dpr={rhi.devicePixelRatioF():.2f} "
        f"fixed={fixed.width()}x{fixed.height()} "
        f"visible={rhi.isVisible()} "
        f"parent={parent_name}"
    )


def _freeze_rhi_surfaces(window) -> None:
    """Pin every QRhiWidget's GPU color buffer to its current size.

    During interactive resize, recreating the swap chain on each pixel event
    is what causes the black-flash and the stutter: the OS compositor shows
    the unrendered backbuffer between widget geometry change and the next
    render(). Pinning the color buffer makes Qt scale the existing surface
    instead of reallocating it; the render at the old size stretches into
    the new geometry until the burst settles.
    """
    for rhi in window.findChildren(QRhiWidget):
        try:
            if not rhi.isVisible():
                _resize_debug(
                    "freeze skip invisible %s %s",
                    _rhi_debug_id(rhi),
                    _rhi_debug_state(rhi),
                )
                continue
            cur = rhi.fixedColorBufferSize()
            if cur.isValid() and cur.width() > 0 and cur.height() > 0:
                _resize_debug(
                    "freeze skip already fixed %s %s",
                    _rhi_debug_id(rhi),
                    _rhi_debug_state(rhi),
                )
                continue
            size = rhi.size()
            if size.width() <= 0 or size.height() <= 0:
                _resize_debug(
                    "freeze skip empty %s %s", _rhi_debug_id(rhi), _rhi_debug_state(rhi)
                )
                continue
            rhi.setFixedColorBufferSize(size)
            _resize_debug(
                "freeze set %s fixed=%dx%d",
                _rhi_debug_id(rhi),
                size.width(),
                size.height(),
            )
        except Exception:
            _resize_debug("freeze failed %s", _rhi_debug_id(rhi), exc_info=True)


def _unfreeze_rhi_surfaces(window) -> None:
    for rhi in window.findChildren(QRhiWidget):
        try:
            rhi.setFixedColorBufferSize(QSize())
            rhi.update()
            _resize_debug("unfreeze %s %s", _rhi_debug_id(rhi), _rhi_debug_state(rhi))
        except Exception:
            _resize_debug("unfreeze failed %s", _rhi_debug_id(rhi), exc_info=True)


def _rhi_background_color(rhi) -> object:
    color = getattr(rhi, "_theme_background_color", None)
    if color is not None and color.isValid():
        return color
    palette = rhi.palette()
    color = palette.color(QPalette.ColorRole.Window)
    if color.isValid():
        return color
    return palette.color(QPalette.ColorRole.Base)


def _rhi_has_uploaded_images(rhi) -> bool:
    runtime_state = getattr(rhi, "runtime_state", None)
    images_uploaded = getattr(runtime_state, "_images_uploaded", ())
    return any(bool(uploaded) for uploaded in images_uploaded)


def _build_rhi_resize_shield_pixmap(rhi) -> QPixmap:
    if _rhi_has_uploaded_images(rhi):
        frame = rhi.grabFramebuffer()
        if not frame.isNull():
            _resize_debug(
                "shield pixmap framebuffer %s frame=%dx%d",
                _rhi_debug_id(rhi),
                frame.width(),
                frame.height(),
            )
            return QPixmap.fromImage(frame)
    pixmap = QPixmap(rhi.size())
    pixmap.fill(_rhi_background_color(rhi))
    _resize_debug(
        "shield pixmap theme-fill %s pixmap=%dx%d has_images=%s",
        _rhi_debug_id(rhi),
        pixmap.width(),
        pixmap.height(),
        _rhi_has_uploaded_images(rhi),
    )
    return pixmap


def _rhi_resize_shield_parent(rhi):
    return rhi.parentWidget() or rhi


def _set_rhi_resize_shield_geometry(rhi, shield) -> None:
    parent = shield.parentWidget()
    if parent is rhi:
        shield.setGeometry(rhi.rect())
        return
    top_left = rhi.mapTo(parent, rhi.rect().topLeft())
    shield.setGeometry(top_left.x(), top_left.y(), rhi.width(), rhi.height())


def _ensure_rhi_resize_shields(window) -> None:
    for rhi in window.findChildren(QRhiWidget):
        try:
            if not rhi.isVisible() or rhi.width() <= 0 or rhi.height() <= 0:
                _resize_debug(
                    "shield skip %s %s", _rhi_debug_id(rhi), _rhi_debug_state(rhi)
                )
                continue
            shield = getattr(rhi, _RESIZE_SHIELD_ATTR, None)
            if shield is None:
                shield_parent = _rhi_resize_shield_parent(rhi)
                shield = QLabel(shield_parent)
                shield.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
                )
                shield.setAutoFillBackground(True)
                shield.setScaledContents(True)
                if _resize_visual_debug_enabled():
                    shield.setText("RESIZE SHIELD")
                    shield.setAlignment(
                        Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
                    )
                    debug_font = shield.font()
                    debug_font.setBold(True)
                    shield.setFont(debug_font)
                    debug_color = QColor(0xFF, 0x17, 0x44)
                    palette = shield.palette()
                    palette.setColor(QPalette.ColorRole.WindowText, debug_color)
                    palette.setColor(
                        QPalette.ColorRole.Window, QColor(0xFF, 0x17, 0x44, 35)
                    )
                    shield.setPalette(palette)
                    shield.setFrameShape(QFrame.Shape.Box)
                    shield.setLineWidth(3)
                else:
                    shield.setPixmap(_build_rhi_resize_shield_pixmap(rhi))
                setattr(rhi, _RESIZE_SHIELD_ATTR, shield)
                _resize_debug(
                    "shield create %s %s shield_parent=%s@%x",
                    _rhi_debug_id(rhi),
                    _rhi_debug_state(rhi),
                    (
                        type(shield_parent).__name__
                        if shield_parent is not None
                        else "None"
                    ),
                    id(shield_parent) if shield_parent is not None else 0,
                )

            _set_rhi_resize_shield_geometry(rhi, shield)
            shield.raise_()
            shield.show()
            _resize_debug(
                "shield show %s shield=%dx%d pos=%d,%d visible=%s parent=%s",
                _rhi_debug_id(rhi),
                shield.width(),
                shield.height(),
                shield.x(),
                shield.y(),
                shield.isVisible(),
                (
                    type(shield.parentWidget()).__name__
                    if shield.parentWidget()
                    else "None"
                ),
            )
        except Exception:
            _resize_debug("shield ensure failed %s", _rhi_debug_id(rhi), exc_info=True)


def _sync_rhi_resize_shields(window) -> None:
    for rhi in window.findChildren(QRhiWidget):
        try:
            shield = getattr(rhi, _RESIZE_SHIELD_ATTR, None)
            if shield is None:
                _resize_debug(
                    "shield sync missing %s %s",
                    _rhi_debug_id(rhi),
                    _rhi_debug_state(rhi),
                )
                continue
            _set_rhi_resize_shield_geometry(rhi, shield)
            shield.raise_()
            _resize_debug(
                "shield sync %s shield=%dx%d pos=%d,%d visible=%s parent=%s",
                _rhi_debug_id(rhi),
                shield.width(),
                shield.height(),
                shield.x(),
                shield.y(),
                shield.isVisible(),
                (
                    type(shield.parentWidget()).__name__
                    if shield.parentWidget()
                    else "None"
                ),
            )
        except Exception:
            _resize_debug("shield sync failed %s", _rhi_debug_id(rhi), exc_info=True)


def _clear_rhi_resize_shields(window) -> None:
    for rhi in window.findChildren(QRhiWidget):
        try:
            shield = getattr(rhi, _RESIZE_SHIELD_ATTR, None)
            if shield is None:
                _resize_debug(
                    "shield clear missing %s %s",
                    _rhi_debug_id(rhi),
                    _rhi_debug_state(rhi),
                )
                continue
            setattr(rhi, _RESIZE_SHIELD_ATTR, None)
            shield.hide()
            shield.deleteLater()
            _resize_debug("shield clear %s", _rhi_debug_id(rhi))
        except Exception:
            _resize_debug("shield clear failed %s", _rhi_debug_id(rhi), exc_info=True)


def _active_image_compare_widget(window):
    return getattr(window, "image_compare_widget", None)


class MainWindowRuntime:
    def __init__(self, window):
        self.window = window

    def handle_debounced_resize(self) -> None:
        window = self.window
        _resize_debug(
            "debounced window=%dx%d in_progress=%s shield_enabled=%s",
            window.width(),
            window.height(),
            window.store.viewport.interaction_state.resize_in_progress,
            _resize_shield_enabled(),
        )
        if _resize_shield_enabled():
            _unfreeze_rhi_surfaces(window)
            _clear_rhi_resize_shields(window)
        if window.store.viewport.interaction_state.resize_in_progress:
            window.store.get_dispatcher().dispatch(
                SetResizeInProgressAction(False), scope="viewport.interaction"
            )
            window.schedule_update()
        if not window.isMaximized() and not window.isFullScreen():
            window.geometry_manager.update_normal_geometry_if_needed()

        window.startup_runtime.sync_cover_geometry()
        widget = _active_image_compare_widget(window)
        if widget is not None:
            widget.image_startup_placeholder.sync_geometry()
            widget.zoom_indicator.sync_position()
        if getattr(window, "onboarding_overlay", None):
            window.onboarding_overlay.resize(window.size())
        if widget is not None:
            widget.update_drag_overlays(
                window.store.viewport.view_state.is_horizontal,
                widget.is_drag_overlay_visible(),
            )

    def handle_resize(self) -> None:
        window = self.window
        self._hide_unified_flyout()
        in_progress = window.store.viewport.interaction_state.resize_in_progress
        _resize_debug(
            "resize window=%dx%d in_progress=%s rhi_count=%d shield_enabled=%s",
            window.width(),
            window.height(),
            in_progress,
            len(window.findChildren(QRhiWidget)),
            _resize_shield_enabled(),
        )
        if not window.store.viewport.interaction_state.resize_in_progress:
            window.store.get_dispatcher().dispatch(
                SetResizeInProgressAction(True), scope="viewport.interaction"
            )
            if _resize_shield_enabled():
                _freeze_rhi_surfaces(window)
                _ensure_rhi_resize_shields(window)
        elif _resize_shield_enabled():
            _sync_rhi_resize_shields(window)
        if not _resize_shield_enabled():
            window.schedule_update()
        window._debounced_resize_timer.start()

    def handle_move(self) -> None:
        window = self.window
        window.startup_runtime.sync_cover_geometry()
        widget = _active_image_compare_widget(window)
        if widget is not None:
            widget.image_startup_placeholder.sync_geometry()
            widget.zoom_indicator.sync_position()
        if getattr(window, "onboarding_overlay", None):
            window.onboarding_overlay.resize(window.size())
        self._hide_unified_flyout()
        if not window.isMaximized() and not window.isFullScreen():
            window.geometry_manager.update_normal_geometry_if_needed()

    def handle_show(self) -> None:
        window = self.window
        window.startup_runtime.sync_cover_geometry()
        widget = _active_image_compare_widget(window)
        if widget is not None:
            widget.image_startup_placeholder.sync_geometry()
            widget.zoom_indicator.sync_position()
        if (
            window.onboarding_overlay is not None
            and not window._startup_visual_ready_emitted
        ):
            window.startup_runtime.emit_visual_ready()
        if window._offscreen_prewarm_active:
            return
        if not window._is_ui_stable:
            QTimer.singleShot(
                50,
                lambda: setattr(window, "_is_ui_stable", True)
                or window.schedule_update(),
            )

    def _hide_unified_flyout(self) -> None:
        window = self.window
        if window.presenter is None:
            return
        flyout = getattr(window.presenter.ui_manager, "unified_flyout", None)
        if flyout is None:
            return
        try:
            flyout.hide()
        except RuntimeError as exc:
            if "UnifiedFlyout has been deleted" in str(exc):
                window.presenter.ui_manager.transient.host.unified_flyout = None
            else:
                raise
