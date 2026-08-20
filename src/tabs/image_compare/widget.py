"""Root widget for the image_compare tab.

The widget is constructed empty by the tab during ``create_page`` (early,
before the host has built the primitive widgets it owns). The host calls
``assemble(ui)`` once those primitives exist; the builder then populates
this widget with the full image-compare layout tree.
"""

from __future__ import annotations

import logging
from typing import Tuple

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget
from sli_ui_toolkit.widgets import ThemedWidget

from sli_ui_toolkit.i18n import tr
from tabs.contract import TabContext
from ui.theming import resolve_theme_color

logger = logging.getLogger("ImproveImgSLI")


class ImageCompareWidget(ThemedWidget, QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        context: TabContext | None = None,
    ):
        super().__init__(parent)
        self._context = context
        self._assembled = False
        self._slot_has_image1 = False
        self._slot_has_image2 = False

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def on_theme_changed(self) -> None:
        self._bg_color = QColor(resolve_theme_color(self._theme_manager, "Window"))
        super().on_theme_changed()

    def assemble(self, ui) -> None:
        if self._assembled:
            return
        from tabs.image_compare.ui.layout import ImageCompareLayoutBuilder

        ImageCompareLayoutBuilder(self, ui).build_into(self)
        self._assembled = True
        self._wire_transition_mask_release()
        self._install_magnifier_settings_flyout()
        self._install_chrome_sync()

    def _install_magnifier_settings_flyout(self) -> None:
        from tabs.image_compare.ui.magnifier_settings_flyout import (
            MagnifierSettingsFlyout,
        )
        from tabs.image_compare.ui.transient_magnifier_settings import (
            MagnifierSettingsHoverController,
        )

        self.magnifier_settings_flyout = MagnifierSettingsFlyout(
            self, self.magnifier_settings_panel
        )
        self._magnifier_settings_hover = MagnifierSettingsHoverController(self)

    def _install_chrome_sync(self) -> None:
        store = getattr(getattr(self, "_context", None), "store", None)
        if store is None:
            return
        from tabs.image_compare.use_cases.chrome_sync import ImageCompareChromeSync

        window = getattr(self._context, "main_window", None)

        def _resolve_window_presenter():
            return getattr(window, "presenter", None) if window is not None else None

        self.chrome_sync = ImageCompareChromeSync(self, store, _resolve_window_presenter)

    def _wire_transition_mask_release(self) -> None:
        canvas = getattr(self, "image_label", None)
        signal = getattr(canvas, "firstVisualFrameReady", None)
        if signal is None:
            return
        try:
            signal.connect(self._on_first_visual_frame)
        except Exception:
            pass
        # Unlike multi_compare's widget.py, nothing here previously dismissed
        # ``image_startup_placeholder`` on the canvas's first real frame --
        # it stayed shown (and raised) over the canvas forever, painted at
        # whatever geometry ``sync_geometry()`` last captured (showEvent
        # time, before layout finishes settling after text-controls-row
        # visibility changes). The gap between that stale geometry and the
        # canvas's final, larger size read as "top of the canvas shows the
        # theme background, only a bottom strip shows the real comparison".
        # Mirror multi_compare's ``_on_first_frame``.
        first_frame_signal = getattr(canvas, "firstFrameRendered", None)
        if first_frame_signal is not None:
            try:
                first_frame_signal.connect(self._on_first_frame_hide_placeholder)
            except Exception:
                pass

    def _on_first_frame_hide_placeholder(self) -> None:
        placeholder = getattr(self, "image_startup_placeholder", None)
        if placeholder is not None:
            placeholder.hide()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Re-size/raise the startup placeholder before the canvas's first paint
        # (unified with multi_compare): at construction it tracked a tiny
        # default-geometry container, and without a resync the canvas would
        # expose its unrendered (transparent) surface on the first frames.
        placeholder = getattr(self, "image_startup_placeholder", None)
        if placeholder is not None:
            placeholder.sync_geometry()
        # firstVisualFrameReady is one-shot; on later tab switches release as
        # soon as this page is shown again if the canvas already painted.
        canvas = getattr(self, "image_label", None)
        already = bool(
            canvas is not None
            and getattr(canvas, "_first_frame_rendered_emitted", False)
        )
        logger.debug(
            "[workspace-transition] IC showEvent already_painted=%s",
            already,
        )
        if already:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._release_transition_mask)
        self._resync_pinned_huds_on_show()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._hide_pinned_huds_on_tab_switch()

    def _hide_pinned_huds_on_tab_switch(self) -> None:
        """Hide this tab's corner HUDs (info + zoom) when the tab itself is hidden.

        ``InfoHUD``/``ZoomIndicator`` are ``pinned`` flyouts reparented onto
        the app-wide ``OverlayLayer`` host (see ``ui/flyout_policy.py``), not
        children of this page widget -- Qt's own ``hideEvent`` on this page
        does not cascade to them, so without this they kept rendering above
        whichever tab/session became active next. ``showEvent`` above
        resyncs them from current state when this tab is shown again.
        """
        for hud in (
            getattr(self, "image_info_hud1", None),
            getattr(self, "image_info_hud2", None),
            getattr(self, "zoom_indicator", None),
        ):
            if hud is not None:
                hud.hide()

    def _resync_pinned_huds_on_show(self) -> None:
        if not getattr(self, "_assembled", False):
            return
        self._sync_info_huds()
        from ui.canvas_infra.viewport.state import get_zoom_level

        self.update_zoom_indicator(get_zoom_level(self.image_label))

    def _on_first_visual_frame(self) -> None:
        logger.debug("[workspace-transition] IC firstVisualFrameReady")
        self._release_transition_mask()

    def _release_transition_mask(self) -> None:
        context = self._context
        services = getattr(context, "services", None) if context else None
        if not services:
            logger.debug(
                "[workspace-transition] IC release skipped: no services "
                "(context=%s)",
                context is not None,
            )
            return
        mask = services.get("workspace.transition_mask")
        if mask is None:
            logger.warning(
                "[workspace-transition] IC release skipped: service "
                "'workspace.transition_mask' missing"
            )
            return
        try:
            logger.debug(
                "[workspace-transition] IC calling mask.release id=%s",
                id(mask),
            )
            mask.release()
        except Exception:
            logger.exception("[workspace-transition] IC mask.release failed")

    # --- image_compare's own update/toggle API (moved out of the host shell) ---

    def apply_icon_sizes(self) -> None:
        self.btn_quick_save.setIconSizePx(24)
        self.help_button.setIconSizePx(24)
        self.btn_clear_list1.setIconSizePx(22)
        self.btn_clear_list2.setIconSizePx(22)
        self.btn_divider_color.setIconSizePx(22)
        self.btn_divider_width.setIconSizePx(22)
        self.btn_magnifier_divider_width.setIconSizePx(22)
        self.btn_magnifier_guides_width.setIconSizePx(22)

    def reapply_button_styles(self) -> None:
        self.apply_icon_sizes()
        for btn in (self.btn_settings, self.btn_quick_save, self.help_button):
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

    def toggle_edit_layout_visibility(self, checked: bool):
        self.edit_layout_widget.setVisible(bool(checked))

    def open_magnifier_settings_flyout(self) -> None:
        flyout = getattr(self, "magnifier_settings_flyout", None)
        group = getattr(self, "magnifier_group_container", None)
        if flyout is None or group is None:
            return
        flyout.show_for_group(group)

    def is_drag_overlay_visible(self) -> bool:
        return self.image_label.is_drag_overlay_visible()

    def update_drag_overlays(self, horizontal: bool = False, visible: bool = False):
        if not self.image_label.isVisible():
            self.drag_overlay.hide()
            return
        lang = self._context.settings.current_language if self._context else "en"
        text1 = tr("image_compare.ui.drop_images_1_here", lang)
        text2 = tr("image_compare.ui.drop_images_2_here", lang)
        self.image_label.set_drag_overlay_state(
            visible=False,
            horizontal=horizontal,
            text1=text1,
            text2=text2,
        )
        self.drag_overlay.set_overlay_state(
            visible=visible,
            target_rect=self.image_label.geometry(),
            horizontal=horizontal,
            text1=text1,
            text2=text2,
        )

    def update_resolution_labels(
        self,
        res1_text: str,
        tooltip1: str,
        res2_text: str,
        tooltip2: str,
        *,
        has_image1: bool,
        has_image2: bool,
    ):
        self.resolution_label1.setText(res1_text)
        self.resolution_label2.setText(res2_text)
        self._slot_has_image1 = has_image1
        self._slot_has_image2 = has_image2
        self._sync_info_huds()

    def update_file_names_display(
        self,
        name1_text: str,
        name2_text: str,
        is_horizontal: bool,
        current_language: str,
        show_labels: bool,
        *,
        has_image1: bool,
        has_image2: bool,
    ):
        self._slot_has_image1 = has_image1
        self._slot_has_image2 = has_image2
        if not show_labels:
            self._hide_file_name_labels()
            self._sync_info_huds()
            return
        self._show_file_name_labels()
        prefix1, prefix2 = self._get_file_name_prefixes(is_horizontal, current_language)
        max_text_width = self._get_max_file_name_width()
        font_metrics = QFontMetrics(self.file_name_label1.font())
        self.file_name_label1.setText(
            self._elide_file_name_text(
                f"{prefix1}: {name1_text}", font_metrics, max_text_width
            )
        )
        self.file_name_label2.setText(
            self._elide_file_name_text(
                f"{prefix2}: {name2_text}", font_metrics, max_text_width
            )
        )
        self._sync_info_huds()

    def _sync_info_huds(self):
        from ui.widgets.flyout_debug import flyout_debug, flyout_debug_enabled

        if flyout_debug_enabled():
            import traceback

            caller = traceback.extract_stack()[-3]
            flyout_debug(
                "_sync_info_huds() called from %s:%d in %s",
                caller.filename,
                caller.lineno,
                caller.name,
            )
        self._apply_info_hud_visibility(self.image_info_hud1, self._slot_has_image1)
        self._apply_info_hud_visibility(self.image_info_hud2, self._slot_has_image2)

    def _apply_info_hud_visibility(self, hud, has_image: bool) -> None:
        """Show/reposition the corner info chip, or hide it when its slot is
        empty — the only condition allowed to close an ``InfoHUD`` (it is
        otherwise pinned + always-on-top, see ``ui/flyout_policy.py``)."""
        if not has_image:
            hud.hide()
            return
        if hud.isVisible():
            hud.reposition()
        else:
            hud.show_on(self.image_label)

    def update_name_length_warning(
        self, warning_text: str, tooltip_text: str, visible: bool
    ):
        self.length_warning_label.setText(warning_text)
        self.length_warning_label.setVisible(visible)

    def update_color_button_tooltip(self, color_name: str, current_language: str):
        tooltip = tr("image_compare.tooltip.magnifier_colors", current_language)
        for attr in (
            "btn_magnifier_color_settings",
            "btn_magnifier_color_settings_beginner",
        ):
            button = getattr(self, attr, None)
            if button is not None:
                button.setToolTip(tooltip)

    def update_combobox_display(
        self,
        image_number: int,
        count: int,
        current_index: int,
        text: str,
        full_path: str,
    ):
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        assert self._context is not None
        store = self._context.store
        assert store is not None
        document = store.get_session_state_slot("document")
        combobox.updateState(
            count,
            current_index,
            text=text,
            items=[
                item.display_name
                for item in (
                    document.image_list1
                    if image_number == 1
                    else document.image_list2
                )
            ],
        )

    def update_zoom_indicator(self, zoom: float):
        pan_x = float(getattr(self.image_label, "pan_offset_x", 0.0) or 0.0)
        pan_y = float(getattr(self.image_label, "pan_offset_y", 0.0) or 0.0)
        self.zoom_indicator.update_zoom(zoom, pan_x, pan_y)

    def update_rating_display(
        self, image_number: int, score: int | None, current_language: str
    ):
        label = self.label_rating1 if image_number == 1 else self.label_rating2
        if score is not None:
            label.setText(f"<b>{score}</b>")
            label.setVisible(True)
        else:
            label.setText("–")
            label.setVisible(False)

    def install_rating_wheel_handlers(self):
        self.label_rating1.wheelEvent = self._make_rating_wheel_handler(1)
        self.label_rating2.wheelEvent = self._make_rating_wheel_handler(2)

    def _make_rating_wheel_handler(self, image_number: int):
        def _wheel(event):
            delta = event.angleDelta().y()
            if delta == 0:
                return
            session_ctrl = self._get_session_controller()
            if session_ctrl is None:
                return
            current_idx = self._get_current_rating_index(image_number)
            if current_idx < 0:
                return
            if delta > 0:
                session_ctrl.increment_rating(image_number, current_idx)
            else:
                session_ctrl.decrement_rating(image_number, current_idx)
            self._refresh_rating_displays()
            event.accept()

        return _wheel

    def _get_session_controller(self):
        main_window = getattr(self._context, "main_window", None)
        controller = getattr(main_window, "main_controller", None)
        if not controller or not hasattr(controller, "sessions"):
            return None
        return controller.sessions

    def _get_current_rating_index(self, image_number: int) -> int:
        assert self._context is not None
        state = self._context.store
        assert state is not None
        return (
            state.document.current_index1
            if image_number == 1
            else state.document.current_index2
        )

    def _refresh_rating_displays(self):
        main_window = getattr(self._context, "main_window", None)
        presenter = getattr(main_window, "presenter", None)
        if presenter is not None:
            presenter.update_rating_displays()

    def _hide_file_name_labels(self):
        self.file_name_label1.setVisible(False)
        self.file_name_label2.setVisible(False)
        self.file_name_label1.setText("")
        self.file_name_label2.setText("")

    def _show_file_name_labels(self):
        self.file_name_label1.setVisible(True)
        self.file_name_label2.setVisible(True)

    def _get_file_name_prefixes(
        self, is_horizontal: bool, current_language: str
    ) -> Tuple[str, str]:
        if not is_horizontal:
            return (
                tr("common.position.left", current_language),
                tr("common.position.right", current_language),
            )
        return (
            tr("image_compare.common.position.top", current_language),
            tr("image_compare.common.position.bottom", current_language),
        )

    def _get_max_file_name_width(self) -> int:
        canvas_width = self.image_label.width() if self.image_label.width() > 0 else 800
        return max(canvas_width // 2 - 40, 80)

    def _elide_file_name_text(
        self, text: str, font_metrics: QFontMetrics, max_text_width: int
    ) -> str:
        if font_metrics.horizontalAdvance(text) > max_text_width:
            return font_metrics.elidedText(
                text, Qt.TextElideMode.ElideRight, max_text_width
            )
        return text