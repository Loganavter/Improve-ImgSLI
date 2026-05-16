from __future__ import annotations

import logging

from PyQt6.QtCore import QTimer

logger = logging.getLogger("ImproveImgSLI")

class MainWindowRuntime:
    def __init__(self, window):
        self.window = window

    def handle_debounced_resize(self) -> None:
        window = self.window
        if window.store.viewport.interaction_state.resize_in_progress:
            window.store.viewport.interaction_state.resize_in_progress = False
            window.schedule_update()
        if not window.isMaximized() and not window.isFullScreen():
            window.geometry_manager.update_normal_geometry_if_needed()

    def handle_resize(self) -> None:
        window = self.window
        window.startup_runtime.sync_cover_geometry()
        if window.ui is not None and hasattr(window.ui, "sync_image_startup_placeholder"):
            window.ui.sync_image_startup_placeholder()

        if getattr(window, "onboarding_overlay", None):
            window.onboarding_overlay.resize(window.size())

        self._hide_unified_flyout()

        if not window.store.viewport.interaction_state.resize_in_progress:
            window.store.viewport.interaction_state.resize_in_progress = True

        if window.ui is not None:
            window.ui.update_drag_overlays(
                window.store.viewport.view_state.is_horizontal,
                window.ui.is_drag_overlay_visible(),
            )
        window._debounced_resize_timer.start()

    def handle_move(self) -> None:
        window = self.window
        window.startup_runtime.sync_cover_geometry()
        if window.ui is not None and hasattr(window.ui, "sync_image_startup_placeholder"):
            window.ui.sync_image_startup_placeholder()
        if getattr(window, "onboarding_overlay", None):
            window.onboarding_overlay.resize(window.size())
        self._hide_unified_flyout()
        if not window.isMaximized() and not window.isFullScreen():
            window.geometry_manager.update_normal_geometry_if_needed()

    def handle_show(self) -> None:
        window = self.window
        if window._offscreen_prewarm_active:
            logger.debug("Main window showEvent (offscreen prewarm)")
        else:
            logger.debug("Main window showEvent")
        window.startup_runtime.sync_cover_geometry()
        if window.ui is not None and hasattr(window.ui, "sync_image_startup_placeholder"):
            window.ui.sync_image_startup_placeholder()
        if window.onboarding_overlay is not None and not window._startup_visual_ready_emitted:
            window.startup_runtime.emit_visual_ready()
        if window._offscreen_prewarm_active:
            return
        if not window._is_ui_stable:
            QTimer.singleShot(
                50,
                lambda: setattr(window, "_is_ui_stable", True) or window.schedule_update(),
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
