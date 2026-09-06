from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from domain.qt_adapters import color_to_qcolor, qcolor_to_color
from tabs.image_compare.canvas.registry import registry
from ui.canvas_infra.scene.property_access import read_canvas_feature_color_by_setting_key
from ui.widgets.color import ColorPickerDialog


class SettingsColorPickerCoordinator:
    def __init__(self, store, main_controller, main_window_app, tr_func):
        self.store = store
        self.main_controller = main_controller
        self.main_window_app = main_window_app
        self.tr = tr_func
        self._dialogs: dict[str, ColorPickerDialog | None] = {}

    def show_canvas_feature_color_picker(
        self,
        *,
        key: str,
        setting_key: str,
        title_key: str,
        on_selected: Callable,
        post_apply: Callable | None = None,
    ):
        self._show_dialog(
            key=key,
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                setting_key,
            ),
            title_key=title_key,
            on_selected=on_selected,
            post_apply=post_apply,
        )

    def show_magnifier_divider_color_picker(self):
        self._show_dialog(
            key="magnifier_divider",
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                "magnifier.divider.color",
            ),
            title_key="image_compare.ui.choose_magnifier_divider_line_color",
            on_selected=self._apply_magnifier_divider_color,
        )

    def show_magnifier_border_color_picker(self):
        self._show_dialog(
            key="magnifier_border",
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                "magnifier.border.color",
            ),
            title_key="image_compare.ui.choose_magnifier_border_color",
            on_selected=self._apply_magnifier_border_color,
        )

    def show_laser_color_picker(self):
        self._show_dialog(
            key="laser",
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                "guides.color",
            ),
            title_key="image_compare.ui.choose_magnifier_guides_color",
            on_selected=self._apply_guides_color,
        )

    def show_capture_ring_color_picker(self):
        self._show_dialog(
            key="capture_ring",
            current_color=read_canvas_feature_color_by_setting_key(
                "image_compare",
                self.store.viewport,
                "capture.color",
            ),
            title_key="image_compare.ui.choose_capture_ring_color",
            on_selected=self._apply_capture_color,
        )

    def show_color_picker(
        self,
        *,
        key: str,
        current_color,
        title_key: str,
        on_selected: Callable,
        post_apply: Callable | None = None,
        show_alpha: bool = True,
        parent_window: QWidget | None = None,
    ) -> None:
        """Open a themed picker for an arbitrary color (not store-backed)."""
        self._show_dialog(
            key=key,
            current_color=current_color,
            title_key=title_key,
            on_selected=on_selected,
            post_apply=post_apply,
            show_alpha=show_alpha,
            parent_window=parent_window,
        )

    def apply_smart_magnifier_colors(self):
        key = "smart_magnifier"
        existing = self._dialogs.get(key)
        if existing and existing.isVisible():
            existing.raise_()
            existing.activateWindow()
            return

        dialog = ColorPickerDialog(
            color_to_qcolor(
                read_canvas_feature_color_by_setting_key(
                    "image_compare",
                    self.store.viewport,
                    "magnifier.divider.color",
                )
            ),
            self.main_window_app,
            title=self.tr("image_compare.ui.choose_magnifier_base_color"),
            show_alpha=True,
        )
        dialog.setModal(False)

        def on_color_selected(color):
            if not color.isValid():
                return

            border_color = QColor(color)
            border_color.setAlpha(230)

            capture_ring_color = QColor(color)
            capture_ring_color.setAlpha(230)

            settings_controller = self._settings_controller()
            if settings_controller is None:
                return

            settings_controller.execute_canvas_feature_alias(
                "overlay.settings.set_border_color",
                qcolor_to_color(border_color),
            )
            self._laser_trace_pick("smart:guides.settings.set_color", QColor(color), "smart")
            settings_controller.execute_canvas_feature_alias(
                "guides.settings.set_color",
                qcolor_to_color(QColor(color)),
            )
            # Keep active magnifier in sync (see _apply_guides_color) via
            # capability alias — no direct feature imports in shared/ui code.
            try:
                store = getattr(self.store, "viewport", None) and self.store
                if store is not None:
                    cmd = registry().get_feature_command_by_alias(
                        "overlay.set_active_guides_color"
                    )
                    if cmd is not None:
                        state_cmd = registry().get_feature_command_by_alias(
                            "overlay.active_state"
                        )
                        model_id = "active"
                        if state_cmd is not None:
                            try:
                                _state = state_cmd(store)
                                if _state is not None:
                                    model_id = _state.get("id", "active")
                            except Exception:
                                pass
                        self._laser_trace_pick("smart:magnifier.guides_color sync", QColor(color), model_id)
                        cmd(store, qcolor_to_color(QColor(color)))
            except Exception:
                pass
            settings_controller.execute_canvas_feature_alias(
                "capture.settings.set_color",
                qcolor_to_color(capture_ring_color),
            )

        dialog.colorSelected.connect(on_color_selected)
        dialog.finished.connect(lambda _result, k=key: self._dialogs.pop(k, None))
        dialog.show()
        self._dialogs[key] = dialog

    def _show_dialog(
        self,
        *,
        key: str,
        current_color,
        title_key: str,
        on_selected: Callable,
        post_apply: Callable | None = None,
        show_alpha: bool = True,
        parent_window: QWidget | None = None,
    ):
        dialog = self._dialogs.get(key)
        if dialog and dialog.isVisible():
            dialog.raise_()
            dialog.activateWindow()
            return

        host = parent_window if parent_window is not None else self.main_window_app
        dialog = ColorPickerDialog(
            color_to_qcolor(current_color),
            host,
            title=self.tr(title_key),
            show_alpha=show_alpha,
        )
        if parent_window is not None:
            dialog.setWindowModality(Qt.WindowModality.WindowModal)
        else:
            dialog.setModal(False)

        def handle_selected(color):
            if not color.isValid():
                return
            on_selected(color)
            if post_apply is not None:
                post_apply(color)

        def on_finished(_result, *, dialog_key=key, transient_host=parent_window):
            self._dialogs.pop(dialog_key, None)
            if transient_host is None:
                return
            try:
                if transient_host.isVisible():
                    from sli_ui_toolkit.ui.widgets.composite.base_flyout.lifecycle import (
                        request_window_activation,
                    )

                    transient_host.raise_()
                    request_window_activation(transient_host, reason="color-finished")
            except RuntimeError:
                return

        dialog.colorSelected.connect(handle_selected)
        dialog.finished.connect(on_finished)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._dialogs[key] = dialog

    def _apply_magnifier_divider_color(self, color):
        settings_controller = self._settings_controller()
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_alias(
                "overlay.settings.set_divider_color",
                qcolor_to_color(color),
            )

    def _apply_magnifier_border_color(self, color):
        settings_controller = self._settings_controller()
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_alias(
                "overlay.settings.set_border_color",
                qcolor_to_color(color),
            )

    def _apply_capture_color(self, color):
        settings_controller = self._settings_controller()
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_alias(
                "capture.settings.set_color",
                qcolor_to_color(color),
            )

    def _apply_guides_color(self, color):
        self._laser_trace_pick("guides.settings.set_color", color, "single")
        settings_controller = self._settings_controller()
        if settings_controller is not None:
            settings_controller.execute_canvas_feature_alias(
                "guides.settings.set_color",
                qcolor_to_color(color),
            )
        # Keep active magnifier's per-instance guides_color in sync, otherwise
        # the toolbar underline (which must show the actually rendered laser color
        # `magnifier.guides_color or guides_state.color` per feature.py:99) stays
        # on the auto-palette blue while the global picker appears to do nothing
        # — the reported "expert mode still blue" mismatch. Via capability
        # alias — no direct feature imports in shared/ui code.
        try:
            store = getattr(self.store, "viewport", None) and self.store
            if store is not None:
                cmd = registry().get_feature_command_by_alias(
                    "overlay.set_active_guides_color"
                )
                if cmd is not None:
                    state_cmd = registry().get_feature_command_by_alias(
                        "overlay.active_state"
                    )
                    model_id = "active"
                    if state_cmd is not None:
                        try:
                            _state = state_cmd(store)
                            if _state is not None:
                                model_id = _state.get("id", "active")
                        except Exception:
                            pass
                    self._laser_trace_pick("magnifier.guides_color sync", color, model_id)
                    cmd(store, qcolor_to_color(color))
        except Exception:
            pass

    def _laser_trace_pick(self, source: str, qcolor: QColor, extra: str = "") -> None:
        try:
            import logging

            from shared.debug_flags import env_flag as _env_flag

            _lg = logging.getLogger("ImproveImgSLI")
            if not _env_flag("IMGSLI_LASER_DEBUG"):
                return
            prefix = "[laser-debug]"
            msg = "pick source=%s color=QColor(r=%s,g=%s,b=%s,a=%s) extra=%s"
            args = (source, qcolor.red(), qcolor.green(), qcolor.blue(), qcolor.alpha(), extra)
            if _env_flag("IMGSLI_LASER_DEBUG"):
                _lg.warning("%s %s", prefix, msg % args)
            else:
                _lg.debug("%s %s", prefix, msg % args)
        except Exception:
            pass

    def _settings_controller(self):
        return getattr(self.main_controller, "settings", None)