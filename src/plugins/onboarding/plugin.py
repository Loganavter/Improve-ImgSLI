from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QStackedWidget

from core.plugin_system import Plugin, plugin
from plugins.onboarding.overlay import OnboardingOverlay

logger = logging.getLogger("ImproveImgSLI")


@plugin(name="onboarding", version="1.0", startup_tier="bootstrap")
class OnboardingPlugin(Plugin):
    """First-run UI-mode picker mounted on the main-window startup stack."""

    capabilities = ("onboarding",)

    def __init__(self) -> None:
        super().__init__()
        self.store: Any | None = None
        self.settings_manager: Any | None = None
        self.event_bus: Any | None = None
        self._window: Any | None = None
        self._overlay: OnboardingOverlay | None = None
        self._on_completed: Callable[[str], None] | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.settings_manager = getattr(context, "settings_manager", None)
        self.event_bus = getattr(context, "event_bus", None)

    def bind_window_shell(self, window_shell: Any) -> None:
        window = getattr(window_shell, "main_window_app", None) or window_shell
        self._window = window
        setattr(window, "onboarding_host", self)

    def should_present(self) -> bool:
        if self.settings_manager is None:
            return False
        return bool(self.settings_manager.is_first_run())

    def is_active(self) -> bool:
        return self._overlay is not None

    def present(
        self,
        window: Any,
        *,
        on_completed: Callable[[str], None] | None = None,
    ) -> None:
        self._window = window
        setattr(window, "onboarding_host", self)
        self._on_completed = on_completed
        stack = getattr(window, "_startup_stack", None)
        if stack is None:
            logger.error("Onboarding present() called without startup stack")
            return

        if self._overlay is None:
            self._overlay = OnboardingOverlay(
                self.settings_manager or getattr(window, "settings_manager", None),
                self.store or getattr(window, "store", None),
                stack,
            )
            self._overlay.completed.connect(self._handle_completed)

        if stack.indexOf(self._overlay) < 0:
            stack.addWidget(self._overlay)

        self._resize_overlay(window, stack)
        self._overlay.prepare_for_display()
        stack.setCurrentWidget(self._overlay)
        self._overlay.raise_()
        self._overlay.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

        hide_cover = getattr(getattr(window, "startup_runtime", None), "hide_cover", None)
        if callable(hide_cover):
            hide_cover()

    def dismiss(self) -> None:
        window = self._window
        overlay = self._overlay
        if overlay is None:
            return
        stack = getattr(window, "_startup_stack", None) if window is not None else None
        if stack is not None:
            try:
                stack.removeWidget(overlay)
            except Exception:
                pass
        overlay.hide()
        overlay.deleteLater()
        self._overlay = None

    def sync_geometry(self) -> None:
        window = self._window
        overlay = self._overlay
        if window is None or overlay is None:
            return
        stack = getattr(window, "_startup_stack", None)
        self._resize_overlay(window, stack)

    def prepare_after_show(self) -> None:
        overlay = self._overlay
        if overlay is not None:
            overlay.prepare_for_display()

    def _resize_overlay(self, window: Any, stack: QStackedWidget | None) -> None:
        overlay = self._overlay
        if overlay is None:
            return
        if stack is not None and stack.width() >= 64 and stack.height() >= 64:
            overlay.resize(stack.size())
            return
        if window.width() < 64 or window.height() < 64:
            return
        title = getattr(window, "_custom_title_bar", None)
        title_h = title.height() if title is not None and title.isVisible() else 36
        if title_h < 8:
            title_h = 36
        overlay.resize(QSize(window.width(), max(64, window.height() - title_h)))

    def _handle_completed(self, mode_key: str) -> None:
        # Dismiss first, then let the host reveal app_host. UI mode is applied
        # by the host *after* the stack switch so layout sees a sized page.
        self.dismiss()
        callback = self._on_completed
        self._on_completed = None
        if callback is not None:
            callback(mode_key)

    def apply_ui_mode(self, mode_key: str) -> None:
        self._apply_ui_mode(mode_key)

    def _apply_ui_mode(self, mode_key: str) -> None:
        window = self._window
        store = self.store
        if store is not None and getattr(store, "settings", None) is not None:
            store.settings.ui_mode = mode_key
        if window is not None and getattr(window, "store", None) is not None:
            window.store.settings.ui_mode = mode_key

        event_bus = self.event_bus
        if event_bus is None and window is not None:
            event_bus = getattr(getattr(window, "app_context", None), "event_bus", None)
        if event_bus is not None:
            try:
                from plugins.settings.events import SettingsUIModeChangedEvent

                event_bus.emit(SettingsUIModeChangedEvent(mode_key))
            except Exception:
                logger.exception("Failed to emit UI mode after onboarding")

        widget = getattr(window, "image_compare_widget", None) if window else None
        if widget is not None and hasattr(widget, "reapply_button_styles"):
            try:
                widget.reapply_button_styles()
            except Exception:
                logger.exception("Failed to reapply toolbar styles after onboarding")
