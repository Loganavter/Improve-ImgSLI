import io
import logging

import PIL.Image
from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QImage, QMouseEvent, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QColorDialog,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from domain.qt_adapters import color_to_qcolor
from plugins.export.models import ExportDialogState
from resources.translations import tr as app_tr
from shared_toolkit.ui.managers.theme_manager import ThemeManager
from shared_toolkit.ui.widgets.atomic import (
    FluentCheckBox,
    FluentComboBox,
    FluentSlider,
)
from shared_toolkit.ui.widgets.atomic.custom_button import CustomButton
from shared_toolkit.ui.widgets.composite import DialogActionBar, OutputPathSection
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

class ExportDialog(QDialog):
    def __init__(
        self,
        dialog_state: ExportDialogState,
        parent=None,
        tr_func=None,
        preview_image: QPixmap | PIL.Image.Image | None = None,
        suggested_filename: str = "",
        on_set_favorite_dir=None,
    ):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("ExportDialog")
        self.tr = tr_func if callable(tr_func) else app_tr
        self.dialog_state = dialog_state
        self.theme_manager = ThemeManager.get_instance()
        self.suggested_filename = suggested_filename
        self._on_set_favorite_dir = on_set_favorite_dir
        self.favorite_dir = dialog_state.favorite_dir

        self.setWindowTitle(
            self.tr("misc.export", self.dialog_state.current_language)
        )
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.resize(860, 540)
        self.setSizeGripEnabled(True)

        self._preview_source_pixmap: QPixmap | None = None

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
        self._apply_styles()
        self.theme_manager.theme_changed.connect(self._apply_styles)

        self._populate_from_state()
        self._suggest_default_filename()
        self._update_controls_visity_by_format()

        QTimer.singleShot(0, self._finalize_layout_and_size)

    def _finalize_layout_and_size(self):
        self._apply_preview_pixmap()

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        left_frame = QFrame()
        left_frame.setFrameShape(QFrame.Shape.StyledPanel)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        preview_title = QLabel(
            self.tr("export.preview", self.dialog_state.current_language)
        )
        preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(QSize(300, 300))
        self.preview_label.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        left_layout.addWidget(preview_title)
        left_layout.addWidget(self.preview_label, 1)

        right_frame = QFrame()
        right_frame.setFrameShape(QFrame.Shape.NoFrame)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(10)

        self.output_section = OutputPathSection(
            directory_label_text=self.tr(
                "label.output_directory", self.dialog_state.current_language
            )
            + ":",
            browse_text=self.tr("button.browse", self.dialog_state.current_language),
            set_favorite_text=self.tr(
                "misc.set_as_favorite", self.dialog_state.current_language
            ),
            use_favorite_text=self.tr(
                "tooltip.use_favorite", self.dialog_state.current_language
            ),
            filename_label_text=self.tr(
                "label.file_name", self.dialog_state.current_language
            )
            + ":",
            on_browse=self._choose_directory,
            on_set_favorite=self._set_favorite_from_current,
            on_use_favorite=self._use_favorite_dir,
            use_custom_line_edit=False,
            filename_editor_factory=QLineEdit,
            button_fixed_height=32,
        )
        self.dir_picker_row = self.output_section.dir_picker_row
        self.edit_dir = self.output_section.edit_dir
        self.btn_browse_dir = self.output_section.btn_browse_dir
        self.favorite_actions = self.output_section.favorite_actions
        self.btn_set_favorite = self.output_section.btn_set_favorite
        self.btn_use_favorite = self.output_section.btn_use_favorite
        self.name_label = self.output_section.filename_label
        self.edit_name = self.output_section.filename_edit

        fmt_label = QLabel(
            self.tr("label.format", self.dialog_state.current_language) + ":"
        )
        self.combo_format = FluentComboBox()
        for fmt in ["PNG", "JPEG", "WEBP", "BMP", "TIFF", "JXL"]:
            self.combo_format.addItem(fmt)
        self.combo_format.currentIndexChanged.connect(
            self._update_controls_visity_by_format
        )

        self.quality_row = QWidget()
        quality_layout = QHBoxLayout(self.quality_row)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.setSpacing(8)
        quality_label = QLabel(
            self.tr("label.quality", self.dialog_state.current_language) + ":"
        )
        self.slider_quality = FluentSlider(Qt.Orientation.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(95)
        self.label_quality_value = QLabel("95")
        self.slider_quality.valueChanged.connect(
            lambda v: self.label_quality_value.setText(str(v))
        )
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.slider_quality, 1)
        quality_layout.addWidget(self.label_quality_value)

        self.png_row = QWidget()
        png_layout = QHBoxLayout(self.png_row)
        png_layout.setContentsMargins(0, 0, 0, 0)
        png_layout.setSpacing(8)
        self.label_png_compress = QLabel(
            self.tr(
                "export.png_compression_level", self.dialog_state.current_language
            )
            + ":"
        )
        self.slider_png_compress = FluentSlider(Qt.Orientation.Horizontal)
        self.slider_png_compress.setRange(0, 9)
        self.slider_png_compress.setValue(9)
        self.label_png_compress_value = QLabel("9")
        self.slider_png_compress.valueChanged.connect(
            lambda v: self.label_png_compress_value.setText(str(v))
        )
        self.checkbox_png_optimize = FluentCheckBox(
            self.tr("export.optimize_png", self.dialog_state.current_language)
        )
        png_layout.addWidget(self.label_png_compress)
        png_layout.addWidget(self.slider_png_compress, 1)
        png_layout.addWidget(self.label_png_compress_value)
        png_layout.addWidget(self.checkbox_png_optimize)

        self.checkbox_fill_bg = FluentCheckBox(
            self.tr("export.fill_background", self.dialog_state.current_language)
        )

        self.btn_bg_color = CustomButton(
            None,
            self.tr("export.background_color", self.dialog_state.current_language),
        )
        self.btn_bg_color.setFixedHeight(32)
        self.btn_bg_color.clicked.connect(self._pick_bg_color)

        self.checkbox_fill_bg.toggled.connect(lambda _: self._apply_preview_pixmap())
        bg_row = QHBoxLayout()
        bg_row.addWidget(self.checkbox_fill_bg)
        bg_row.addWidget(self.btn_bg_color)
        self.current_bg_color = QColor(255, 255, 255, 255)

        self.checkbox_include_metadata = FluentCheckBox(
            self.tr("export.include_metadata", self.dialog_state.current_language)
        )
        self.checkbox_include_metadata.toggled.connect(
            self._on_include_metadata_toggled
        )

        self.comment_label = QLabel(
            self.tr("export.comment", self.dialog_state.current_language) + ":"
        )
        self.edit_comment = QLineEdit()
        self.checkbox_comment_default = FluentCheckBox(
            self.tr("export.remember_by_default", self.dialog_state.current_language)
        )

        self.action_bar = DialogActionBar(
            self.tr("common.ok", self.dialog_state.current_language),
            self.tr("common.cancel", self.dialog_state.current_language),
            primary_min_size=(100, 36),
            secondary_min_size=(100, 36),
        )
        self.btn_ok = self.action_bar.primary_button
        self.btn_cancel = self.action_bar.secondary_button
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        right_layout.addWidget(self.output_section)
        right_layout.addSpacing(6)
        right_layout.addWidget(fmt_label)
        right_layout.addWidget(self.combo_format)
        right_layout.addWidget(self.quality_row)
        right_layout.addWidget(self.png_row)
        right_layout.addLayout(bg_row)
        right_layout.addWidget(self.checkbox_include_metadata)
        right_layout.addWidget(self.comment_label)
        right_layout.addWidget(self.edit_comment)
        right_layout.addWidget(self.checkbox_comment_default)
        right_layout.addStretch()
        right_layout.addWidget(self.action_bar)

        main_layout.addWidget(left_frame, 1)
        main_layout.addWidget(right_frame, 0)

        self._on_include_metadata_toggled(self.checkbox_include_metadata.isChecked())

    def _apply_styles(self):

        self.theme_manager.apply_theme_to_dialog(self)

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
        self.checkbox_fill_bg.setChecked(bool(self.dialog_state.fill_background))

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
            self.tr(
                "export.select_output_directory", self.dialog_state.current_language
            )
        )
        file_dialog.setDirectory(start_dir)

        self.theme_manager.apply_theme_to_dialog(file_dialog)

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

    def _pick_bg_color(self):
        color = QColorDialog.getColor(
            (
                self.current_bg_color
                if isinstance(self.current_bg_color, QColor)
                else QColor(255, 255, 255, 255)
            ),
            self,
            self.tr(
                "export.select_background_color", self.dialog_state.current_language
            ),
        )
        if color.isValid():
            self.current_bg_color = color
            self._apply_preview_pixmap()

    def _update_controls_visity_by_format(self):
        fmt = self.combo_format.currentText().upper()
        lossy = fmt in ("JPEG", "WEBP", "JXL")
        self.quality_row.setVisible(lossy)
        self.png_row.setVisible(fmt == "PNG")

        has_transparency = fmt in ("PNG", "TIFF", "WEBP", "JXL")
        self.checkbox_fill_bg.setEnabled(has_transparency)
        self.checkbox_fill_bg.setVisible(has_transparency)

        self._apply_preview_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_preview_pixmap()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_preview_pixmap()

    def _apply_preview_pixmap(self):

        if self._preview_source_pixmap is None or self._preview_source_pixmap.isNull():

            self.preview_label.clear()
            return

        target_size = self.preview_label.size()
        if target_size.isEmpty():
            target_size = self.preview_label.minimumSize()
            if target_size.isEmpty():
                target_size = QSize(300, 300)

        fmt_current = (
            self.combo_format.currentText().upper()
            if hasattr(self, "combo_format")
            else "PNG"
        )
        formats_with_alpha = {"PNG", "TIFF", "WEBP", "JXL"}
        force_fill = fmt_current not in formats_with_alpha
        effective_fill = bool(self.checkbox_fill_bg.isChecked()) or force_fill

        scaled = self._preview_source_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if effective_fill:
            composed = QPixmap(scaled.size())
            composed.fill(
                self.current_bg_color
                if isinstance(self.current_bg_color, QColor)
                else QColor(255, 255, 255, 255)
            )
            painter = QPainter(composed)
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
                    data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888
                )
                if not qimage.isNull():
                    return QPixmap.fromImage(qimage)
            elif pil_img.mode == "RGB":
                data = pil_img.tobytes("raw", "RGB")
                qimage = QImage(
                    data, pil_img.width, pil_img.height, QImage.Format.Format_RGB888
                )
                if not qimage.isNull():
                    return QPixmap.fromImage(qimage)

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
        fmt = self.combo_format.currentText().upper()
        bg = (
            self.current_bg_color
            if isinstance(self.current_bg_color, QColor)
            else QColor(255, 255, 255, 255)
        )
        return {
            "output_dir": self.edit_dir.text().strip(),
            "file_name": self.edit_name.text().strip(),
            "format": fmt,
            "quality": int(self.slider_quality.value()),
            "fill_background": bool(self.checkbox_fill_bg.isChecked()),
            "background_color": (bg.red(), bg.green(), bg.blue(), bg.alpha()),
            "png_compress_level": int(self.slider_png_compress.value()),
            "png_optimize": bool(self.checkbox_png_optimize.isChecked()),
            "include_metadata": bool(self.checkbox_include_metadata.isChecked()),
            "comment_text": self.edit_comment.text().strip(),
            "comment_keep_default": bool(self.checkbox_comment_default.isChecked()),
        }

    def accept(self):
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
