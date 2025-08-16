from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QFrame,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QComboBox,
    QCheckBox,
    QSlider,
    QWidget,
    QColorDialog,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QPixmap, QColor, QIcon, QPainter, QImage
import PIL.Image
from PIL.ImageQt import ImageQt
import io
import os
import re
import logging

from core.theme import ThemeManager
from utils.resource_loader import resource_path
from ui.widgets import FluentCheckBox, FluentSlider

try:
    from resources.translations import tr as app_tr
except ImportError:
    def app_tr(text, lang="en", *args, **kwargs):
        try:
            return text.format(*args, **kwargs)
        except (KeyError, IndexError):
            return text

logger = logging.getLogger("ImproveImgSLI")

class ExportDialog(QDialog):
    def __init__(self, app_state, parent=None, tr_func=None, preview_image: QPixmap | PIL.Image.Image | None = None, suggested_filename: str = ""):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("ExportDialog")
        self.tr = tr_func if callable(tr_func) else app_tr
        self.app_state = app_state
        self.theme_manager = ThemeManager.get_instance()
        self.suggested_filename = suggested_filename

        self.setWindowTitle(self.tr("Export", self.app_state.current_language))
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint
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
                        logger.warning("Preview image conversion resulted in a null QPixmap.")
                        self._preview_source_pixmap = None
                except Exception as e:
                    logger.error(f"Failed to convert preview PIL image to QPixmap: {e}", exc_info=True)
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

        preview_title = QLabel(self.tr("Preview", self.app_state.current_language))
        preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(QSize(300, 300))
        self.preview_label.setFrameShape(QFrame.Shape.NoFrame)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        left_layout.addWidget(preview_title)
        left_layout.addWidget(self.preview_label, 1)

        right_frame = QFrame()
        right_frame.setFrameShape(QFrame.Shape.NoFrame)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(10)

        dir_label = QLabel(self.tr("Output directory:", self.app_state.current_language))
        self.edit_dir = QLineEdit()
        self.btn_browse_dir = QPushButton(self.tr("Browse...", self.app_state.current_language))
        self.btn_browse_dir.clicked.connect(self._choose_directory)

        dir_row = QHBoxLayout()
        dir_row.addWidget(self.edit_dir, 1)
        dir_row.addWidget(self.btn_browse_dir)

        fav_row = QHBoxLayout()
        self.btn_set_favorite = QPushButton(self.tr("Set as Favorite", self.app_state.current_language))
        self.btn_use_favorite = QPushButton(self.tr("Use Favorite", self.app_state.current_language))
        self.btn_set_favorite.clicked.connect(self._set_favorite_from_current)
        self.btn_use_favorite.clicked.connect(self._use_favorite_dir)
        fav_row.addWidget(self.btn_set_favorite)
        fav_row.addWidget(self.btn_use_favorite)

        name_label = QLabel(self.tr("File name:", self.app_state.current_language))
        self.edit_name = QLineEdit()

        fmt_label = QLabel(self.tr("Format:", self.app_state.current_language))
        self.combo_format = QComboBox()
        for fmt in ["PNG", "JPEG", "WEBP", "BMP", "TIFF"]:
            self.combo_format.addItem(fmt)
        self.combo_format.currentIndexChanged.connect(self._update_controls_visity_by_format)

        self.quality_row = QWidget()
        quality_layout = QHBoxLayout(self.quality_row)
        quality_layout.setContentsMargins(0, 0, 0, 0)
        quality_layout.setSpacing(8)
        quality_label = QLabel(self.tr("Quality:", self.app_state.current_language))
        self.slider_quality = FluentSlider(Qt.Orientation.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(95)
        self.label_quality_value = QLabel("95")
        self.slider_quality.valueChanged.connect(lambda v: self.label_quality_value.setText(str(v)))
        quality_layout.addWidget(quality_label)
        quality_layout.addWidget(self.slider_quality, 1)
        quality_layout.addWidget(self.label_quality_value)

        self.png_row = QWidget()
        png_layout = QHBoxLayout(self.png_row)
        png_layout.setContentsMargins(0, 0, 0, 0)
        png_layout.setSpacing(8)
        self.label_png_compress = QLabel(self.tr("PNG Compression Level:", self.app_state.current_language))
        self.slider_png_compress = FluentSlider(Qt.Orientation.Horizontal)
        self.slider_png_compress.setRange(0, 9)
        self.slider_png_compress.setValue(9)
        self.label_png_compress_value = QLabel("9")
        self.slider_png_compress.valueChanged.connect(lambda v: self.label_png_compress_value.setText(str(v)))
        self.checkbox_png_optimize = FluentCheckBox(self.tr("Optimize PNG", self.app_state.current_language))
        png_layout.addWidget(self.label_png_compress)
        png_layout.addWidget(self.slider_png_compress, 1)
        png_layout.addWidget(self.label_png_compress_value)
        png_layout.addWidget(self.checkbox_png_optimize)

        self.checkbox_fill_bg = FluentCheckBox(self.tr("Fill background", self.app_state.current_language))
        self.btn_bg_color = QPushButton(self.tr("Background Color", self.app_state.current_language))
        self.btn_bg_color.clicked.connect(self._pick_bg_color)
        self.checkbox_fill_bg.toggled.connect(lambda _: self._apply_preview_pixmap())
        bg_row = QHBoxLayout()
        bg_row.addWidget(self.checkbox_fill_bg)
        bg_row.addWidget(self.btn_bg_color)
        self.current_bg_color = QColor(255, 255, 255, 255)

        self.checkbox_include_metadata = FluentCheckBox(self.tr("Include metadata", self.app_state.current_language))
        self.checkbox_include_metadata.toggled.connect(self._on_include_metadata_toggled)

        self.comment_label = QLabel(self.tr("Comment:", self.app_state.current_language))
        self.edit_comment = QLineEdit()
        self.checkbox_comment_default = FluentCheckBox(self.tr("Remember by default", self.app_state.current_language))

        btns_row = QHBoxLayout()
        btns_row.addStretch()
        self.btn_ok = QPushButton(self.tr("OK", self.app_state.current_language))
        self.btn_cancel = QPushButton(self.tr("Cancel", self.app_state.current_language))
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.setObjectName("okButton")
        btns_row.addWidget(self.btn_ok)
        btns_row.addWidget(self.btn_cancel)

        right_layout.addWidget(dir_label)
        right_layout.addLayout(dir_row)
        right_layout.addLayout(fav_row)
        right_layout.addSpacing(6)
        right_layout.addWidget(name_label)
        right_layout.addWidget(self.edit_name)
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
        right_layout.addLayout(btns_row)

        main_layout.addWidget(left_frame, 1)
        main_layout.addWidget(right_frame, 0)

        self._on_include_metadata_toggled(self.checkbox_include_metadata.isChecked())

    def _apply_styles(self):

        self.update()

    def _populate_from_state(self):
        out_dir = self.app_state.export_default_dir if self.app_state.export_use_default_dir and self.app_state.export_default_dir else None
        if not out_dir:
            out_dir = self._get_os_default_downloads()
        self.edit_dir.setText(out_dir)

        fmt = (self.app_state.export_last_format or "PNG").upper()
        idx = self.combo_format.findText(fmt)
        if idx >= 0:
            self.combo_format.setCurrentIndex(idx)
        self.slider_quality.setValue(int(self.app_state.export_quality or self.app_state.jpeg_quality or 95))
        self.label_quality_value.setText(str(self.slider_quality.value()))
        self.slider_png_compress.setValue(int(getattr(self.app_state, "export_png_compress_level", 9)))
        self.label_png_compress_value.setText(str(int(getattr(self.app_state, "export_png_compress_level", 9))))
        self.checkbox_png_optimize.setChecked(True)

        if hasattr(self.app_state, "export_background_color") and isinstance(self.app_state.export_background_color, QColor):
            self.current_bg_color = self.app_state.export_background_color
        self.checkbox_fill_bg.setChecked(bool(getattr(self.app_state, "export_fill_background", False)))

        self.checkbox_include_metadata.setChecked(True)

        self.edit_comment.setText(getattr(self.app_state, "export_comment_text", "") or "")
        self.checkbox_comment_default.setChecked(bool(getattr(self.app_state, "export_comment_keep_default", False)))

    def _suggest_default_filename(self):
        self.edit_name.setText(self.suggested_filename or "comparison")

    def _choose_directory(self):
        start_dir = self.edit_dir.text() or self._get_os_default_downloads()
        chosen = QFileDialog.getExistingDirectory(self, self.tr("Select Output Directory", self.app_state.current_language), start_dir)
        if chosen:
            self.edit_dir.setText(chosen)

    def _set_favorite_from_current(self):
        path = self.edit_dir.text().strip()
        if path:
            self.app_state.export_favorite_dir = path

    def _use_favorite_dir(self):
        path = getattr(self.app_state, "export_favorite_dir", None)
        if path:
            self.edit_dir.setText(path)

    def _pick_bg_color(self):
        color = QColorDialog.getColor(self.current_bg_color if isinstance(self.current_bg_color, QColor) else QColor(255,255,255,255), self, self.tr("Select Background Color", self.app_state.current_language))
        if color.isValid():
            self.current_bg_color = color
            self._apply_preview_pixmap()

    def _update_controls_visity_by_format(self):
        fmt = self.combo_format.currentText().upper()
        lossy = fmt in ("JPEG", "WEBP")
        self.quality_row.setVisible(lossy)
        self.png_row.setVisible(fmt == "PNG")

        has_transparency = fmt in ("PNG", "TIFF", "WEBP")
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

        fmt_current = self.combo_format.currentText().upper() if hasattr(self, "combo_format") else "PNG"
        formats_with_alpha = {"PNG", "TIFF", "WEBP"}
        force_fill = fmt_current not in formats_with_alpha
        effective_fill = bool(self.checkbox_fill_bg.isChecked()) or force_fill

        scaled = self._preview_source_pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if effective_fill:
            composed = QPixmap(scaled.size())
            composed.fill(self.current_bg_color if isinstance(self.current_bg_color, QColor) else QColor(255,255,255,255))
            painter = QPainter(composed)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            self.preview_label.setPixmap(composed)
        else:
            self.preview_label.setPixmap(scaled)

    def _pixmap_from_pil(self, pil_img: PIL.Image.Image) -> QPixmap:
        try:

            if pil_img.mode == 'RGBA':
                data = pil_img.tobytes("raw", "RGBA")
                qimage = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGBA8888)
                if not qimage.isNull():
                    return QPixmap.fromImage(qimage)
            elif pil_img.mode == 'RGB':
                data = pil_img.tobytes("raw", "RGB")
                qimage = QImage(data, pil_img.width, pil_img.height, QImage.Format.Format_RGB888)
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

    def _get_os_default_downloads(self) -> str:
        home = os.path.expanduser("~")
        candidates = []
        try:
            user_dirs = os.path.join(home, ".config", "user-dirs.dirs")
            if os.path.exists(user_dirs):
                with open(user_dirs, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.startswith("XDG_DOWNLOAD_DIR"):
                            parts = line.split("=")
                            if len(parts) == 2:
                                path_val = parts[1].strip().strip('"')
                                path_val = path_val.replace("$HOME", home)
                                candidates.append(path_val)
                            break
        except Exception:
            pass
        candidates += [
            os.path.join(home, "Downloads"),
            os.path.join(home, "Загрузки"),
            home,
        ]
        for p in candidates:
            try:
                if os.path.isdir(p):
                    return p
            except Exception:
                continue
        return home

    def get_export_options(self) -> dict:
        fmt = self.combo_format.currentText().upper()
        bg = self.current_bg_color if isinstance(self.current_bg_color, QColor) else QColor(255, 255, 255, 255)
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

        if hasattr(self, 'comment_label'):
            self.comment_label.setVisible(checked)
        if hasattr(self, 'edit_comment'):
            self.edit_comment.setVisible(checked)
        if hasattr(self, 'checkbox_comment_default'):
            self.checkbox_comment_default.setVisible(checked)
