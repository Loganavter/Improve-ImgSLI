import io
import logging

import PIL.Image
import shiboken6 as sip
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QImage, QMouseEvent, QPainter, QPixmap
from shared_toolkit.ui.themed_dialog import ThemedDialog
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QLineEdit,
)

from domain.qt_adapters import color_to_qcolor
from plugins.export.dialog_sections import assemble_export_ui
from plugins.export.layout_geometry import apply_export_dialog_geometry
from plugins.export.models import ExportDialogState
from resources.translations import tr as app_tr
from shared_toolkit.ui.layout_sizing import handle_application_font_change
from sli_ui_toolkit.i18n import translatable_text, translatable_tooltip
from sli_ui_toolkit.managers import SettleGate
from sli_ui_toolkit.theme import ThemeManager
from ui.theming import polish_themed_dialog
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")


class ExportDialog(ThemedDialog):
    def __init__(
        self,
        dialog_state: ExportDialogState,
        parent=None,
        tr_func=None,
        preview_image: QPixmap | PIL.Image.Image | None = None,
        suggested_filename: str = "",
        on_set_favorite_dir=None,
        native_size: tuple[int, int] | None = None,
    ):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("ExportDialog")
        # Never assign to ``self.tr`` — QObject.tr() is Qt's own API and
        # shadowing it makes translations look like raw keys.
        self._tr_func = tr_func if callable(tr_func) else app_tr
        self.dialog_state = dialog_state
        self.theme_manager = ThemeManager.get_instance()
        self.suggested_filename = suggested_filename
        self._on_set_favorite_dir = on_set_favorite_dir
        self.favorite_dir = dialog_state.favorite_dir
        self._export_options_cache: dict | None = None

        nw, nh = native_size if native_size and native_size[0] > 0 and native_size[1] > 0 else (0, 0)
        self._native_width = int(nw)
        self._native_height = int(nh)
        self._aspect_ratio = (self._native_width / self._native_height) if self._native_height else 0.0
        self._suppress_ratio_recalc = False
        try:
            self._initial_scale = max(0.05, float(getattr(dialog_state, "resolution_scale", 1.0) or 1.0))
        except (TypeError, ValueError):
            self._initial_scale = 1.0

        self.setWindowTitle(self._tr("misc.export", "Export"))
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)

        self._preview_source_pixmap: QPixmap | None = None
        # Cheap pixmap scale on pulse; quiet-period re-apply for final pane size.
        self._preview_resize_settle = SettleGate(
            on_settle=self._apply_preview_pixmap,
            on_pulse=self._apply_preview_pixmap,
            interval_ms=SettleGate.DEFAULT_INTERVAL_MS,
            parent=self,
        )

        if preview_image is not None:
            if isinstance(preview_image, QPixmap):
                self._preview_source_pixmap = preview_image.copy()
            elif isinstance(preview_image, PIL.Image.Image):
                try:
                    self._preview_source_pixmap = self._pixmap_from_pil(preview_image)
                    if self._preview_source_pixmap.isNull():
                        logger.warning(
                            "Preview image conversion resulted in a null QPixmap."
                        )
                        self._preview_source_pixmap = None
                except Exception as e:
                    logger.error(
                        f"Failed to convert preview PIL image to QPixmap: {e}",
                        exc_info=True,
                    )
                    self._preview_source_pixmap = None

        self._init_ui()
        self._bind_translations()
        self._reapply_bound_texts()
        self.install_dialog_geometry(self._apply_dialog_geometry)
        self.mark_theme_ui_ready()
        from shared_toolkit.ui.decorate_dialog import decorate_dialog, install_dialog_help_menu
        decorate_dialog(self, title=self._tr("misc.export", "Export"))
        install_dialog_help_menu(self, page="export")

        self._populate_from_state()
        self._suggest_default_filename()
        self._update_controls_visity_by_format()

        for line_edit in (self.edit_dir, self.edit_name, self.edit_comment):
            line_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
            line_edit.returnPressed.connect(line_edit.clearFocus)
        self.setFocus()

        self.finished.connect(self._withdraw_find_actions)
        self._contribute_find_actions()
        QTimer.singleShot(0, self._finalize_layout_and_size)

    def _tr(self, key: str, default: str | None = None) -> str:
        lang = self.dialog_state.current_language or "en"
        text = self._tr_func(key, lang)
        if text == key and default is not None:
            return default
        return text

    def _tr_for_bind(self, key: str, language: str | None = None) -> str:
        """Adapter for ``translatable_text`` / ``translatable_tooltip``.

        Prefer the dialog's language (``dialog_state``) so the first bind pass
        does not depend on whether the global TranslationManager language has
        already been emitted.
        """
        lang = self.dialog_state.current_language or language or "en"
        text = self._tr_func(key, lang)
        return text

    def _apply_dialog_geometry(self) -> None:
        apply_export_dialog_geometry(self)

    def changeEvent(self, event):
        handle_application_font_change(self, event)
        super().changeEvent(event)

    def update_language(self, language: str) -> None:
        self.dialog_state.current_language = language or "en"
        self.setWindowTitle(self._tr("misc.export", "Export"))
        title_bar = getattr(self, "_csd_title_bar", None)
        if title_bar is not None and hasattr(title_bar, "set_title"):
            title_bar.set_title(self._tr("misc.export", "Export"))
        # Re-apply bound texts for the new dialog language (bind helpers read
        # dialog_state, so a no-op callback refresh is enough via setters).
        self._reapply_bound_texts()
        self._apply_dialog_geometry()

    def _reapply_bound_texts(self) -> None:
        """Force bound widgets to the current ``dialog_state`` language."""
        pairs = (
            (self.export_preview_title, "export.preview", ""),
            (self.output_section.dir_label, "label.output_directory", ":"),
            (self.btn_browse_dir, "button.browse", ""),
            (self.btn_set_favorite, "misc.set_as_favorite", ""),
            (self.btn_use_favorite, "tooltip.use_favorite", ""),
            (self.name_label, "label.file_name", ":"),
            (self.fmt_label, "label.format", ":"),
            (self.resolution_label, "label.resolution", ":"),
            (self.quality_label, "label.quality", ":"),
            (self.label_png_compress, "export.png_compression_level", ":"),
            (self.checkbox_png_optimize, "export.optimize_png", ""),
            (self.checkbox_fill_bg, "export.fill_background", ""),
            (self.btn_bg_color, "export.background_color", ""),
            (self.checkbox_include_metadata, "export.include_metadata", ""),
            (self.comment_label, "export.comment", ":"),
            (self.checkbox_comment_default, "export.remember_by_default", ""),
            (self.btn_ok, "common.ok", ""),
            (self.btn_cancel, "common.cancel", ""),
        )
        for widget, key, suffix in pairs:
            widget.setText(self._tr(key, key) + suffix)
        self.btn_lock_ratio.setToolTip(
            self._tr("export.lock_aspect_ratio", "Lock aspect ratio")
        )
        if hasattr(self.action_bar, "_apply_button_minimums"):
            self.action_bar._apply_button_minimums()
        if hasattr(self.action_bar, "lock_content_minimum_height"):
            self.action_bar.lock_content_minimum_height()
        self._harden_text_buttons(
            self.btn_browse_dir,
            self.btn_set_favorite,
            self.btn_use_favorite,
            self.btn_bg_color,
        )
        if hasattr(self, "output_section"):
            self.output_section.lock_content_minimum_height()

    @staticmethod
    def _harden_text_buttons(*buttons) -> None:
        """Keep text buttons from collapsing below their content sizeHint.

        Do not use ``setFixedHeight`` here — toolkit text buttons hint at
        ``fontMetrics.height() + 16`` (often > 32), and a tighter fixed height
        clips the bottom edge / corner radius.
        """
        from PySide6.QtWidgets import QSizePolicy

        for button in buttons:
            if button is None:
                continue
            # Drop any leftover fixed-height clamp from construction.
            button.setMinimumHeight(0)
            button.setMaximumHeight(16777215)
            hint = button.sizeHint()
            button.setMinimumSize(
                max(button.minimumWidth(), hint.width()),
                max(32, hint.height()),
            )
            button.setSizePolicy(
                QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
            )

    def _finalize_layout_and_size(self):
        self._apply_preview_pixmap()
        # Force computed size: CSD adjustSize may already have overgrown from
        # the preview pixmap before this deferred pass runs.
        apply_export_dialog_geometry(self, force_resize=True)
        try:
            from sli_ui_toolkit.ui.windows.csd_helpers import sync_csd_chrome

            sync_csd_chrome(self)
        except Exception:
            pass

    def _bind_translations(self) -> None:
        trb = self._tr_for_bind
        translatable_text(self.export_preview_title, "export.preview", tr_func=trb)
        translatable_text(
            self.output_section.dir_label,
            "label.output_directory",
            suffix=":",
            tr_func=trb,
        )
        translatable_text(self.btn_browse_dir, "button.browse", tr_func=trb)
        translatable_text(self.btn_set_favorite, "misc.set_as_favorite", tr_func=trb)
        translatable_text(self.btn_use_favorite, "tooltip.use_favorite", tr_func=trb)
        translatable_text(
            self.name_label, "label.file_name", suffix=":", tr_func=trb
        )
        translatable_text(self.fmt_label, "label.format", suffix=":", tr_func=trb)
        translatable_text(
            self.resolution_label, "label.resolution", suffix=":", tr_func=trb
        )
        translatable_tooltip(
            self.btn_lock_ratio, "export.lock_aspect_ratio", tr_func=trb
        )
        translatable_text(
            self.quality_label, "label.quality", suffix=":", tr_func=trb
        )
        translatable_text(
            self.label_png_compress,
            "export.png_compression_level",
            suffix=":",
            tr_func=trb,
        )
        translatable_text(
            self.checkbox_png_optimize, "export.optimize_png", tr_func=trb
        )
        translatable_text(
            self.checkbox_fill_bg, "export.fill_background", tr_func=trb
        )
        translatable_text(
            self.btn_bg_color, "export.background_color", tr_func=trb
        )
        translatable_text(
            self.checkbox_include_metadata, "export.include_metadata", tr_func=trb
        )
        translatable_text(
            self.comment_label, "export.comment", suffix=":", tr_func=trb
        )
        translatable_text(
            self.checkbox_comment_default,
            "export.remember_by_default",
            tr_func=trb,
        )
        translatable_text(self.btn_ok, "common.ok", tr_func=trb)
        translatable_text(self.btn_cancel, "common.cancel", tr_func=trb)

    def _init_ui(self):
        assemble_export_ui(self)

    def _populate_from_state(self):
        self.edit_dir.setText(self.dialog_state.output_dir)

        fmt = (self.dialog_state.last_format or "PNG").upper()
        idx = self.combo_format.findText(fmt)
        if idx >= 0:
            self.combo_format.setCurrentIndex(idx)
        self.slider_quality.setValue(int(self.dialog_state.quality or 95))
        self.label_quality_value.setText(str(self.slider_quality.value()))
        self.slider_png_compress.setValue(
            int(self.dialog_state.png_compress_level or 9)
        )
        self.label_png_compress_value.setText(
            str(int(self.dialog_state.png_compress_level or 9))
        )
        self.checkbox_png_optimize.setChecked(True)

        if self.dialog_state.background_color is not None:
            self.current_bg_color = color_to_qcolor(self.dialog_state.background_color)
        # Desired preference from settings; _update_controls_visity_by_format
        # clears/disables when virtual canvas is inactive.
        self.checkbox_fill_bg.setChecked(bool(self.dialog_state.fill_background))
        self._sync_background_controls()

        self.checkbox_include_metadata.setChecked(True)

        self.edit_comment.setText(self.dialog_state.comment_text or "")
        self.checkbox_comment_default.setChecked(bool(self.dialog_state.comment_keep_default))

    def _suggest_default_filename(self):
        self.edit_name.setText(self.suggested_filename or "comparison")

    def _choose_directory(self):
        start_dir = self.edit_dir.text().strip() or self.dialog_state.output_dir
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.Directory)
        file_dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        file_dialog.setWindowTitle(
            self._tr("export.select_output_directory", "Select Output Directory")
        )
        file_dialog.setDirectory(start_dir)

        polish_themed_dialog(self.theme_manager, file_dialog)

        if file_dialog.exec():
            chosen = (
                file_dialog.selectedFiles()[0] if file_dialog.selectedFiles() else ""
            )
            if chosen:
                self.edit_dir.setText(chosen)

    def _set_favorite_from_current(self):
        path = self.edit_dir.text().strip()
        if path:
            self.favorite_dir = path
            if callable(self._on_set_favorite_dir):
                self._on_set_favorite_dir(path)

    def _use_favorite_dir(self):
        path = self.favorite_dir
        if path:
            self.edit_dir.setText(path)

    def _fill_background_allowed(self) -> bool:
        """Fill only when pads exist (virtual canvas past 0..1) and format has alpha."""
        fmt = (
            self.combo_format.currentText().upper()
            if hasattr(self, "combo_format")
            else "PNG"
        )
        has_transparency = fmt in ("PNG", "TIFF", "WEBP", "JXL")
        return has_transparency and bool(
            getattr(self.dialog_state, "virtual_canvas_active", True)
        )

    def _on_fill_background_toggled(self, _checked: bool = False) -> None:
        self._sync_background_controls()
        self._apply_preview_pixmap()

    def _sync_background_controls(self) -> None:
        """Color picker is only active while fill is enabled (or forced by format)."""
        fmt = (
            self.combo_format.currentText().upper()
            if hasattr(self, "combo_format")
            else "PNG"
        )
        has_transparency = fmt in ("PNG", "TIFF", "WEBP", "JXL")
        fill_allowed = self._fill_background_allowed()
        fill_active = (
            bool(self.checkbox_fill_bg.isChecked()) if fill_allowed else (not has_transparency)
        )
        btn = getattr(self, "btn_bg_color", None)
        if btn is None:
            return
        btn.setEnabled(fill_active)
        # Plain picker — never leave a latch/checked glow when fill is off.
        set_checked = getattr(btn, "setChecked", None)
        if callable(set_checked):
            try:
                set_checked(False, emit=False)
            except TypeError:
                set_checked(False)

    def _pick_bg_color(self):
        if hasattr(self, "btn_bg_color") and not self.btn_bg_color.isEnabled():
            return
        color = QColorDialog.getColor(
            (
                self.current_bg_color
                if isinstance(self.current_bg_color, QColor)
                else QColor(255, 255, 255, 255)
            ),
            self,
            self._tr("export.select_background_color", "Select Background Color"),
        )
        if color.isValid():
            self.current_bg_color = color
            self._sync_background_controls()
            self._apply_preview_pixmap()

    def _update_controls_visity_by_format(self):
        fmt = self.combo_format.currentText().upper()
        lossy = fmt in ("JPEG", "WEBP", "JXL")
        self.quality_row.setVisible(lossy)
        self.png_row.setVisible(fmt == "PNG")

        has_transparency = fmt in ("PNG", "TIFF", "WEBP", "JXL")
        fill_allowed = self._fill_background_allowed()
        self.checkbox_fill_bg.setVisible(has_transparency)
        self.checkbox_fill_bg.setEnabled(fill_allowed)
        if has_transparency and not fill_allowed:
            # Unit canvas (0..1): no pads to paint — keep fill off.
            self.checkbox_fill_bg.blockSignals(True)
            self.checkbox_fill_bg.setChecked(False)
            self.checkbox_fill_bg.blockSignals(False)
        elif fill_allowed and not self.checkbox_fill_bg.isChecked():
            # Restore settings preference when pads become relevant again
            # (format switch back to alpha with an active virtual canvas).
            if bool(self.dialog_state.fill_background):
                self.checkbox_fill_bg.blockSignals(True)
                self.checkbox_fill_bg.setChecked(True)
                self.checkbox_fill_bg.blockSignals(False)
        self._sync_background_controls()

        self._apply_preview_pixmap()
        self._apply_dialog_geometry()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # CSD startSystemResize can ignore QWidget/QWindow minimumSize on some
        # compositors — pull the window back so form controls are not crushed.
        min_size = self.minimumSize()
        if self.width() < min_size.width() or self.height() < min_size.height():
            if not getattr(self, "_restoring_min_size", False):
                self._restoring_min_size = True

                def _restore() -> None:
                    try:
                        if sip.isValid(self):
                            self.resize(
                                max(self.width(), min_size.width()),
                                max(self.height(), min_size.height()),
                            )
                    finally:
                        self._restoring_min_size = False

                QTimer.singleShot(0, _restore)
            return
        self._preview_resize_settle.ping()

    def showEvent(self, event):
        super().showEvent(event)
        handle = self.windowHandle()
        if handle is not None:
            handle.setMinimumSize(self.minimumSize())
        try:
            from sli_ui_toolkit.ui.windows.csd_helpers import sync_csd_chrome

            sync_csd_chrome(self)
        except Exception:
            pass
        # Deferred geometry may land after first show; rebuild CSD mask once
        # more on the next tick so corner arcs cannot punch through the body.
        QTimer.singleShot(0, self._sync_csd_chrome_safe)
        self._apply_preview_pixmap()
        self._contribute_find_actions()

    def _contribute_find_actions(self) -> None:
        try:
            from plugins.export.actions import (
                _export_dialog_owner_tab,
                contribute_export_dialog_actions,
            )
            from ui.actions.palette import install_dialog_find_action_shortcut

            owner = _export_dialog_owner_tab()
            contribute_export_dialog_actions(self, owner_tab=owner)
            install_dialog_find_action_shortcut(self, active_tab=owner)
        except Exception:
            logger.debug(
                "[find-action] export_dialog _contribute_find_actions failed",
                exc_info=True,
            )

    def _withdraw_find_actions(self, *_args) -> None:
        try:
            from plugins.export.actions import withdraw_export_dialog_actions

            withdraw_export_dialog_actions()
        except Exception:
            logger.debug(
                "[find-action] export_dialog _withdraw_find_actions failed",
                exc_info=True,
            )
    def _sync_csd_chrome_safe(self) -> None:
        if not sip.isValid(self):
            return
        try:
            from sli_ui_toolkit.ui.windows.csd_helpers import sync_csd_chrome

            sync_csd_chrome(self)
        except Exception:
            pass

    def _apply_preview_pixmap(self):

        if self._preview_source_pixmap is None or self._preview_source_pixmap.isNull():

            self.preview_label.clear()
            return

        target_size = self.preview_label.size()
        if target_size.isEmpty():
            target_size = self.preview_label.minimumSize()
            if target_size.isEmpty():
                target_size = QSize(
                    export_geo.EXPORT_PREVIEW_MIN_WIDTH,
                    export_geo.EXPORT_PREVIEW_MIN_HEIGHT,
                )

        fmt_current = (
            self.combo_format.currentText().upper()
            if hasattr(self, "combo_format")
            else "PNG"
        )
        formats_with_alpha = {"PNG", "TIFF", "WEBP", "JXL"}
        force_fill = fmt_current not in formats_with_alpha
        fill_allowed = self._fill_background_allowed()
        effective_fill = (
            force_fill
            or (fill_allowed and bool(self.checkbox_fill_bg.isChecked()))
        )
        bg = (
            self.current_bg_color
            if isinstance(self.current_bg_color, QColor)
            else QColor(255, 255, 255, 255)
        )

        scaled = self._preview_source_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if effective_fill:
            # Fill only the export frame (virtual canvas). Label chrome around
            # the KeepAspectRatio letterbox stays the theme preview surface.
            composed = QPixmap(scaled.size())
            composed.fill(bg)
            painter = QPainter(composed)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            self.preview_label.setPixmap(composed)
        else:
            self.preview_label.setPixmap(scaled)

    def _pixmap_from_pil(self, pil_img: PIL.Image.Image) -> QPixmap:
        try:

            if pil_img.mode == "RGBA":
                data = pil_img.tobytes("raw", "RGBA")
                qimage = QImage(
                    data,
                    pil_img.width,
                    pil_img.height,
                    pil_img.width * 4,
                    QImage.Format.Format_RGBA8888,
                )
                if not qimage.isNull():
                    # Own the pixels — ``data`` is a temporary Python buffer.
                    return QPixmap.fromImage(qimage.copy())
            elif pil_img.mode == "RGB":
                data = pil_img.tobytes("raw", "RGB")
                qimage = QImage(
                    data,
                    pil_img.width,
                    pil_img.height,
                    pil_img.width * 3,
                    QImage.Format.Format_RGB888,
                )
                if not qimage.isNull():
                    return QPixmap.fromImage(qimage.copy())

            buf = io.BytesIO()
            pil_img.save(buf, format="PNG")
            data = buf.getvalue()
            pix = QPixmap()
            pix.loadFromData(data, "PNG")
            return pix
        except Exception as e:
            logger.error(f"Error converting PIL Image to QPixmap: {e}", exc_info=True)
            return QPixmap()

    def get_export_options(self) -> dict:
        if not sip.isValid(self):
            return dict(self._export_options_cache or {})
        if hasattr(self, "edit_dir") and not sip.isValid(self.edit_dir):
            return dict(self._export_options_cache or {})
        return self._snapshot_export_options()

    def _snapshot_export_options(self) -> dict:
        fmt = self.combo_format.currentText().upper()
        bg = (
            self.current_bg_color
            if isinstance(self.current_bg_color, QColor)
            else QColor(255, 255, 255, 255)
        )
        opts = {
            "output_dir": self.edit_dir.text().strip(),
            "file_name": self.edit_name.text().strip(),
            "format": fmt,
            "quality": int(self.slider_quality.value()),
            "fill_background": (
                bool(self.checkbox_fill_bg.isChecked())
                if self._fill_background_allowed()
                else False
            ),
            "fill_background_editable": self._fill_background_allowed(),
            "virtual_canvas_active": bool(
                getattr(self.dialog_state, "virtual_canvas_active", True)
            ),
            "background_color": (bg.red(), bg.green(), bg.blue(), bg.alpha()),
            "png_compress_level": int(self.slider_png_compress.value()),
            "png_optimize": bool(self.checkbox_png_optimize.isChecked()),
            "include_metadata": bool(self.checkbox_include_metadata.isChecked()),
            "comment_text": self.edit_comment.text().strip(),
            "comment_keep_default": bool(self.checkbox_comment_default.isChecked()),
        }
        try:
            w = int(self.edit_width.text())
            h = int(self.edit_height.text())
            if w > 0 and h > 0:
                opts["width"] = w
                opts["height"] = h
                if self._native_width > 0:
                    opts["resolution_scale"] = w / float(self._native_width)
        except (ValueError, AttributeError):
            pass
        return opts

    def _on_width_edited(self):
        if self._suppress_ratio_recalc:
            return
        text = self.edit_width.text().strip()
        if not text:
            self._reset_resolution_to_native()
            return
        try:
            w = int(text)
        except ValueError:
            return
        if w <= 0:
            self._reset_resolution_to_native()
            return
        if self.btn_lock_ratio.isChecked() and self._aspect_ratio > 0:
            new_h = max(1, int(round(w / self._aspect_ratio)))
            self._suppress_ratio_recalc = True
            self.edit_height.setText(str(new_h))
            self._suppress_ratio_recalc = False

    def _on_height_edited(self):
        if self._suppress_ratio_recalc:
            return
        text = self.edit_height.text().strip()
        if not text:
            self._reset_resolution_to_native()
            return
        try:
            h = int(text)
        except ValueError:
            return
        if h <= 0:
            self._reset_resolution_to_native()
            return
        if self.btn_lock_ratio.isChecked() and self._aspect_ratio > 0:
            new_w = max(1, int(round(h * self._aspect_ratio)))
            self._suppress_ratio_recalc = True
            self.edit_width.setText(str(new_w))
            self._suppress_ratio_recalc = False

    def _reset_resolution_to_native(self):
        if self._native_width <= 0 or self._native_height <= 0:
            return
        self._suppress_ratio_recalc = True
        self.edit_width.setText(str(self._native_width))
        self.edit_height.setText(str(self._native_height))
        self._suppress_ratio_recalc = False

    def accept(self):
        self._export_options_cache = self._snapshot_export_options()
        super().accept()

    def _on_include_metadata_toggled(self, checked: bool):

        if hasattr(self, "comment_label"):
            self.comment_label.setVisible(checked)
        if hasattr(self, "edit_comment"):
            self.edit_comment.setVisible(checked)
        if hasattr(self, "checkbox_comment_default"):
            self.checkbox_comment_default.setVisible(checked)

    def mousePressEvent(self, event: QMouseEvent):
        self.clear_input_focus()
        super().mousePressEvent(event)

    def clear_input_focus(self):
        focused_widget = self.focusWidget()
        if focused_widget and isinstance(focused_widget, QLineEdit):
            focused_widget.clearFocus()
