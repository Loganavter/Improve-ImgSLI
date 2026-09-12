import logging

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QIcon
from shared_toolkit.ui.themed_dialog import ThemedDialog

from plugins.settings.dialog_context import SettingsDialogContext
from plugins.settings.dialog_shell import (
    apply_styles,
    calculate_and_apply_geometry,
    create_scrollable_page,
    defer_geometry,
    page_scroll_area,
    setup_dialog_shell,
    setup_sidebar_items,
)
from plugins.settings.registry import (
    ensure_tab_settings_contributions,
    get_settings_registry,
)
from plugins.settings.models import SettingsDialogData
from resources.translations import tr as app_tr
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import CustomGroupWidget
from ui.icon_manager import AppIcon
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

class SettingsDialog(ThemedDialog):
    """Settings chrome. OK applies and keeps the window open; Cancel closes."""

    settings_confirmed = Signal()

    def __init__(
        self,
        current_language,
        current_theme,
        current_max_length,
        min_limit,
        max_limit,
        debug_mode_enabled,
        system_notifications_enabled,
        current_resolution_limit,
        parent=None,
        tr_func=None,
        current_ui_font_mode: str = "builtin",
        current_ui_font_family: str = "",
        current_ui_mode: str = "beginner",
        optimize_magnifier_movement: bool = True,
        movement_interpolation_method: str = "BILINEAR",
        optimize_laser_smoothing: bool = False,
        interpolation_method: str = "LANCZOS",
        zoom_interpolation_method: str = "BILINEAR",
        magnifier_intersection_highlight_enabled: bool = True,
        magnifier_auto_color_new_instances: bool = True,
        auto_calculate_psnr: bool = False,
        auto_calculate_ssim: bool = False,
        auto_crop_black_borders: bool = True,
        current_video_fps: int = 60,
        rhi_backend: str = "default",
        store=None,
        active_tab: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("SettingsDialog")
        self.tr = tr_func if callable(tr_func) else app_tr
        self.current_language = current_language
        self.theme_manager = ThemeManager.get_instance()
        self.context = SettingsDialogContext(
            current_language=current_language,
            current_theme=current_theme,
            current_max_length=current_max_length,
            min_limit=min_limit,
            max_limit=max_limit,
            debug_mode_enabled=debug_mode_enabled,
            system_notifications_enabled=system_notifications_enabled,
            current_resolution_limit=current_resolution_limit,
            tr_func=self.tr,
            current_ui_font_mode=current_ui_font_mode,
            current_ui_font_family=current_ui_font_family,
            current_ui_mode=current_ui_mode,
            optimize_magnifier_movement=optimize_magnifier_movement,
            movement_interpolation_method=movement_interpolation_method,
            optimize_laser_smoothing=optimize_laser_smoothing,
            interpolation_method=interpolation_method,
            zoom_interpolation_method=zoom_interpolation_method,
            magnifier_intersection_highlight_enabled=magnifier_intersection_highlight_enabled,
            magnifier_auto_color_new_instances=magnifier_auto_color_new_instances,
            auto_calculate_psnr=auto_calculate_psnr,
            auto_calculate_ssim=auto_calculate_ssim,
            auto_crop_black_borders=auto_crop_black_borders,
            current_video_fps=current_video_fps,
            rhi_backend=rhi_backend,
            store=store,
            keyboard_overrides=dict(
                getattr(getattr(store, "settings", None), "keyboard_overrides", {}) or {}
            )
            if store is not None
            else {},
            tab_extras=get_settings_registry().seed_payloads(store),
        )
        self._custom_group_widget_cls = CustomGroupWidget

        self.setWindowTitle(self.tr("misc.settings", self.current_language))
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)

        from PySide6.QtWidgets import QHBoxLayout

        self.main_layout = QHBoxLayout(self)
        setup_dialog_shell(self)
        from shared_toolkit.ui.decorate_dialog import decorate_dialog
        decorate_dialog(self, title=self.tr("misc.settings", self.current_language))
        self.active_tab = active_tab
        ensure_tab_settings_contributions()
        self._active_sections = get_settings_registry().sections_for(active_tab)
        for section in self._active_sections:
            section.build(self, self.context)
        self._setup_sidebar_items()
        self.install_dialog_geometry(self._calculate_and_apply_geometry)
        self.mark_theme_ui_ready()
        self.sidebar.setCurrentRow(0)
        calculate_and_apply_geometry(self)

        from resources.translations import translation_events

        # Stay open after Apply — retranslate chrome when language is confirmed.
        translation_events().language_changed.connect(self.update_language)

    def select_section(self, section_id: str) -> None:
        """Select a sidebar page by ``SettingsSection.section_id``."""
        if not section_id:
            return
        sections = getattr(self, "_active_sections", None) or ()
        for index, section in enumerate(sections):
            if section.section_id == section_id:
                self.sidebar.setCurrentRow(index)
                return

    def sidebar_row_widget_for(self, section_id: str):
        """Return the nav-row button for ``section_id``, or ``None``.

        Uses toolkit ``IconListWidget.row_button`` so Find Action can pulse the
        sidebar without poking row internals.
        """
        if not section_id:
            return None
        sections = getattr(self, "_active_sections", None) or ()
        sidebar = getattr(self, "sidebar", None)
        if sidebar is None:
            return None
        row_button = getattr(sidebar, "row_button", None)
        for index, section in enumerate(sections):
            if section.section_id != section_id:
                continue
            if callable(row_button):
                return row_button(index)
            # Older toolkit: fall back through item proxy.
            item = sidebar.item(index)
            if item is None:
                return None
            spec = getattr(item, "_spec", None)
            return getattr(spec, "button", None) if spec is not None else None
        return None

    def group_widget_for(self, group_key: str):
        """Return the ``CustomGroupWidget`` tagged with ``group_key``, or ``None``.

        Scrolls the group into the page viewport so Find Action pulse is visible.
        """
        if not group_key:
            return None
        from PySide6.QtWidgets import QWidget
        from plugins.settings.member_resolve import scroll_widget_into_view
        from ui.actions.search_index import PROP_GROUP

        for child in self.findChildren(QWidget):
            if child.property(PROP_GROUP) == group_key:
                scroll_widget_into_view(child)
                return child
        return None

    def member_widget_for(self, group_key: str, member_key: str):
        """Return a tagged control inside ``group_key`` (or the dialog), prepared for reveal."""
        from plugins.settings.member_resolve import resolve_member_widget

        return resolve_member_widget(self, group_key, member_key)

    def changeEvent(self, event: QEvent):
        if event.type() == QEvent.Type.ApplicationFontChange:
            defer_geometry(self)
        super().changeEvent(event)

    def _calculate_and_apply_geometry(self):
        calculate_and_apply_geometry(self)

    def _setup_sidebar_items(self):
        setup_sidebar_items(self)

    def _update_sidebar_icons(self):
        self.sidebar.refresh_icons()

    def _create_scrollable_page(self):
        return create_scrollable_page()

    def _page_scroll_area(self, page):
        return page_scroll_area(page)

    def _on_category_changed(self, row):
        self.pages_stack.setCurrentIndex(row)
        self._update_sidebar_icons()

    def on_dialog_theme_changed(self) -> None:
        self._update_sidebar_icons()

    def _apply_styles(self):
        apply_styles(self)

    def get_settings(self):
        selected_language = next(
            (
                lang
                for radio, lang in {
                    self.radio_en: "en",
                    self.radio_ru: "ru",
                    self.radio_zh: "zh",
                    self.radio_pt_br: "pt_BR",
                }.items()
                if radio.isChecked()
            ),
            "en",
        )
        ui_font_mode = next(
            (
                mode
                for radio, mode in {
                    self.radio_font_system_default: "system_default",
                    self.radio_font_system_custom: "system_custom",
                }.items()
                if radio.isChecked()
            ),
            "builtin",
        )
        ui_mode = next(
            (
                mode
                for radio, mode in {
                    self.radio_ui_mode_expert: "expert",
                    self.radio_ui_mode_advanced: "advanced",
                }.items()
                if radio.isChecked()
            ),
            "beginner",
        )

        def _val(attr, default):
            widget = getattr(self, attr, None)
            if widget is None:
                return default
            # Order matters: sli_ui_toolkit ComboBox inherits from a button-like
            # base and exposes isChecked() (always False) — currentData must win.
            # Same for SpinBox having a button base under the hood.
            if hasattr(widget, "currentData"):
                return widget.currentData()
            if hasattr(widget, "value") and not hasattr(widget, "isChecked"):
                return widget.value()
            if hasattr(widget, "isChecked"):
                return widget.isChecked()
            if hasattr(widget, "value"):
                return widget.value()
            return default

        ctx = self.context
        return SettingsDialogData(
            language=selected_language,
            theme=self.combo_theme.currentData(),
            max_name_length=self.spin_max_length.value(),
            debug_enabled=self.debug_checkbox.isChecked(),
            system_notifications_enabled=self.system_notifications_checkbox.isChecked(),
            resolution_limit=_val("combo_resolution", ctx.current_resolution_limit),
            ui_font_mode=ui_font_mode,
            ui_font_family=self.combo_font_family.currentData() or "",
            optimize_magnifier_movement=_val(
                "optimize_movement_checkbox", ctx.optimize_magnifier_movement
            ),
            magnifier_interpolation_method=_val(
                "combo_mag_interp", ctx.movement_interpolation_method
            ) or "BILINEAR",
            optimize_laser_smoothing=_val(
                "laser_smoothing_checkbox", ctx.optimize_laser_smoothing
            ),
            laser_interpolation_method=_val(
                "combo_laser_interp", "BILINEAR"
            ) or "BILINEAR",
            zoom_interpolation_method=_val(
                "combo_zoom_interp", ctx.zoom_interpolation_method
            ) or "BILINEAR",
            magnifier_intersection_highlight_enabled=_val(
                "magnifier_intersection_highlight_checkbox",
                ctx.magnifier_intersection_highlight_enabled,
            ),
            magnifier_auto_color_new_instances=_val(
                "magnifier_auto_color_checkbox",
                ctx.magnifier_auto_color_new_instances,
            ),
            auto_calculate_psnr=(
                self.auto_psnr_checkbox.isChecked()
                if hasattr(self, "auto_psnr_checkbox")
                else self.context.auto_calculate_psnr
            ),
            auto_calculate_ssim=(
                self.auto_ssim_checkbox.isChecked()
                if hasattr(self, "auto_ssim_checkbox")
                else self.context.auto_calculate_ssim
            ),
            auto_crop_black_borders=(
                self.crop_checkbox.isChecked()
                if hasattr(self, "crop_checkbox")
                else self.context.auto_crop_black_borders
            ),
            ui_mode=ui_mode,
            video_recording_fps=_val("spin_fps", ctx.current_video_fps),
            rhi_backend=(_val("combo_rhi_backend", ctx.rhi_backend) or "default"),
            keyboard_overrides=dict(
                getattr(self, "_keyboard_overrides", None)
                or getattr(ctx, "keyboard_overrides", None)
                or {}
            ),
            tab_extras=get_settings_registry().read_payloads(self),
        )

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        self.context.current_language = lang_code
        from plugins.settings.translations import apply_translations

        apply_translations(self, lang_code)
        try:
            from plugins.settings.pages import keyboard as keyboard_page

            keyboard_page.refresh_language(self)
        except Exception:
            logger.exception("Settings keyboard page retranslation failed")
        self._setup_sidebar_items()
        curr = self.sidebar.currentRow()
        self.sidebar.setCurrentRow(-1)
        self.sidebar.setCurrentRow(curr)
        defer_geometry(self)

    def confirm_settings(self):
        """Apply current values without closing the dialog."""
        self._reset_button_states()
        self.settings_confirmed.emit()

    def sync_from_store(self) -> None:
        """Re-read live store values into general toggles before showing."""
        store = getattr(self.context, "store", None)
        settings = getattr(store, "settings", None) if store is not None else None
        if settings is None:
            return
        notifications = bool(
            getattr(settings, "system_notifications_enabled", True)
        )
        debug_enabled = bool(getattr(settings, "debug_mode_enabled", False))
        self.context.system_notifications_enabled = notifications
        self.context.debug_mode_enabled = debug_enabled
        checkbox = getattr(self, "system_notifications_checkbox", None)
        if checkbox is not None:
            checkbox.setChecked(notifications)
        debug_cb = getattr(self, "debug_checkbox", None)
        if debug_cb is not None:
            debug_cb.setChecked(debug_enabled)

    def accept(self):
        self.confirm_settings()

    def reject(self):
        self._reset_button_states()
        super().reject()

    def _reset_button_states(self):
        if hasattr(self, "ok_button"):
            self.ok_button.setProperty("state", "normal")
            self.ok_button.update()
        if hasattr(self, "cancel_button"):
            self.cancel_button.setProperty("state", "normal")
            self.cancel_button.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clear_input_focus()
        super().mousePressEvent(event)

    def clear_input_focus(self):
        focused_widget = self.focusWidget()
        if focused_widget and hasattr(focused_widget, "clearFocus"):
            focused_widget.clearFocus()
