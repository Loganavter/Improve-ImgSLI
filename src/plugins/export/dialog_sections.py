"""Widget-tree builders for ExportDialog.

Mirrors the video_editor ``dialog_sections`` pattern: builders attach widgets
to ``dialog.*`` attributes; the dialog owns lifecycle, signals targets, and
geometry via ``layout_geometry``.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIntValidator
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.constants import AppConstants
from plugins.export import layout_geometry as export_geo
from plugins.export.search import ACTIONS, BACKGROUND, OUTPUT, RESOLUTION
from sli_ui_toolkit.widgets import (
    Button,
    CheckBox,
    ComboBox,
    Slider,
)
from ui.icon_manager import AppIcon
from ui.widgets.form_controls import DialogActionBar, OutputPathSection


class _ExportPreviewLabel(QLabel):
    """Preview surface whose sizeHint ignores the pixmap.

    A normal QLabel reports the pixmap size as sizeHint; after CSD
    ``adjustSize`` that blows the dialog up to hundreds of px and makes
    ``EXPORT_PREVIEW_MIN_WIDTH`` look like a no-op.
    """

    def sizeHint(self) -> QSize:
        return QSize(
            max(self.minimumWidth(), export_geo.EXPORT_PREVIEW_MIN_WIDTH),
            max(self.minimumHeight(), export_geo.EXPORT_PREVIEW_MIN_HEIGHT),
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


def build_preview_pane(dialog) -> QFrame:
    left_frame = QFrame()
    left_frame.setObjectName("ExportPreviewFrame")
    dialog.export_preview_frame = left_frame
    left_layout = QVBoxLayout(left_frame)
    left_layout.setContentsMargins(8, 8, 8, 8)
    left_layout.setSpacing(8)

    dialog.export_preview_title = QLabel(dialog._tr("export.preview", "Preview"))
    dialog.export_preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.preview_label = _ExportPreviewLabel()
    dialog.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.preview_label.setMinimumSize(
        QSize(
            export_geo.EXPORT_PREVIEW_MIN_WIDTH,
            export_geo.EXPORT_PREVIEW_MIN_HEIGHT,
        )
    )
    dialog.preview_label.setFrameShape(QFrame.Shape.NoFrame)
    dialog.preview_label.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
    )

    left_layout.addWidget(dialog.export_preview_title)
    left_layout.addWidget(dialog.preview_label, 1)
    return left_frame


def build_output_path_section(dialog) -> None:
    dialog.output_section = OutputPathSection(
        directory_label_text=dialog._tr("label.output_directory", "Output directory")
        + ":",
        browse_text=dialog._tr("button.browse", "Browse..."),
        set_favorite_text=dialog._tr("misc.set_as_favorite", "Set as Favorite"),
        use_favorite_text=dialog._tr("tooltip.use_favorite", "Use Favorite"),
        filename_label_text=dialog._tr("label.file_name", "File name") + ":",
        on_browse=dialog._choose_directory,
        on_set_favorite=dialog._set_favorite_from_current,
        on_use_favorite=dialog._use_favorite_dir,
        use_custom_line_edit=False,
        filename_editor_factory=QLineEdit,
    )
    dialog.dir_picker_row = dialog.output_section.dir_picker_row
    dialog.edit_dir = dialog.output_section.edit_dir
    dialog.btn_browse_dir = dialog.output_section.btn_browse_dir
    dialog.favorite_actions = dialog.output_section.favorite_actions
    dialog.btn_set_favorite = dialog.output_section.btn_set_favorite
    dialog.btn_use_favorite = dialog.output_section.btn_use_favorite
    dialog.name_label = dialog.output_section.filename_label
    dialog.edit_name = dialog.output_section.filename_edit
    OUTPUT.tag_member(dialog.btn_browse_dir, "button.browse")
    OUTPUT.tag_member(dialog.btn_set_favorite, "misc.set_as_favorite")
    OUTPUT.tag_member(dialog.btn_use_favorite, "tooltip.use_favorite")
    dialog._harden_text_buttons(
        dialog.btn_browse_dir,
        dialog.btn_set_favorite,
        dialog.btn_use_favorite,
    )
    dialog.output_section.lock_content_minimum_height()


def build_format_row(dialog) -> None:
    dialog.fmt_label = QLabel(dialog._tr("label.format", "Format") + ":")
    dialog.combo_format = ComboBox()
    for fmt in ["PNG", "JPEG", "WEBP", "BMP", "TIFF", "JXL"]:
        dialog.combo_format.addItem(fmt)
    dialog.combo_format.currentIndexChanged.connect(
        dialog._update_controls_visity_by_format
    )


def build_resolution_row(dialog) -> None:
    dialog.resolution_row = QWidget()
    res_layout = QHBoxLayout(dialog.resolution_row)
    res_layout.setContentsMargins(0, 0, 0, 0)
    res_layout.setSpacing(8)
    dialog.resolution_label = QLabel(
        dialog._tr("label.resolution", "Resolution") + ":"
    )
    res_layout.addWidget(dialog.resolution_label)
    dialog.edit_width = QLineEdit()
    _max_dim = int(AppConstants.MAX_SUPPORTED_IMAGE_DIMENSION)
    dialog.edit_width.setValidator(QIntValidator(1, _max_dim))
    dialog.edit_width.setFixedWidth(72)
    dialog.edit_width.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.edit_height = QLineEdit()
    dialog.edit_height.setValidator(QIntValidator(1, _max_dim))
    dialog.edit_height.setFixedWidth(72)
    dialog.edit_height.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dialog.btn_lock_ratio = Button(
        icon=(AppIcon.UNLINK, AppIcon.LINK), toggle=True, size=(32, 32)
    )
    dialog.btn_lock_ratio.setChecked(True)
    RESOLUTION.tag_member(dialog.btn_lock_ratio, "export.lock_aspect_ratio")
    res_layout.addWidget(dialog.edit_width)
    res_layout.addWidget(dialog.btn_lock_ratio)
    res_layout.addWidget(dialog.edit_height)
    res_layout.addStretch()

    if dialog._native_width > 0 and dialog._native_height > 0:
        initial_w = max(1, int(round(dialog._native_width * dialog._initial_scale)))
        initial_h = max(1, int(round(dialog._native_height * dialog._initial_scale)))
    else:
        initial_w, initial_h = 1920, 1080
    dialog.edit_width.setText(str(initial_w))
    dialog.edit_height.setText(str(initial_h))
    dialog.edit_width.editingFinished.connect(dialog._on_width_edited)
    dialog.edit_height.editingFinished.connect(dialog._on_height_edited)
    dialog.resolution_row.setVisible(
        dialog._native_width > 0 and dialog._native_height > 0
    )


def build_quality_controls(dialog) -> None:
    dialog.quality_row = QWidget()
    quality_layout = QHBoxLayout(dialog.quality_row)
    quality_layout.setContentsMargins(0, 0, 0, 0)
    quality_layout.setSpacing(8)
    dialog.quality_label = QLabel(dialog._tr("label.quality", "Quality") + ":")
    dialog.slider_quality = Slider(Qt.Orientation.Horizontal)
    dialog.slider_quality.setRange(1, 100)
    dialog.slider_quality.setValue(95)
    dialog.label_quality_value = QLabel("95")
    dialog.slider_quality.valueChanged.connect(
        lambda v: dialog.label_quality_value.setText(str(v))
    )
    quality_layout.addWidget(dialog.quality_label)
    quality_layout.addWidget(dialog.slider_quality, 1)
    quality_layout.addWidget(dialog.label_quality_value)


def build_png_options(dialog) -> None:
    dialog.png_row = QWidget()
    png_layout = QHBoxLayout(dialog.png_row)
    png_layout.setContentsMargins(0, 0, 0, 0)
    png_layout.setSpacing(8)
    dialog.label_png_compress = QLabel(
        dialog._tr("export.png_compression_level", "PNG Compression Level") + ":"
    )
    dialog.slider_png_compress = Slider(Qt.Orientation.Horizontal)
    dialog.slider_png_compress.setRange(0, 9)
    dialog.slider_png_compress.setValue(9)
    dialog.label_png_compress_value = QLabel("9")
    dialog.slider_png_compress.valueChanged.connect(
        lambda v: dialog.label_png_compress_value.setText(str(v))
    )
    dialog.checkbox_png_optimize = CheckBox(
        dialog._tr("export.optimize_png", "Optimize PNG")
    )
    png_layout.addWidget(dialog.label_png_compress)
    png_layout.addWidget(dialog.slider_png_compress, 1)
    png_layout.addWidget(dialog.label_png_compress_value)
    png_layout.addWidget(dialog.checkbox_png_optimize)


def build_background_row(dialog) -> None:
    dialog.checkbox_fill_bg = CheckBox(
        dialog._tr("export.fill_background", "Fill background")
    )

    dialog.btn_bg_color = Button(
        text=dialog._tr("export.background_color", "Background Color"),
        variant="surface",
    )
    dialog.btn_bg_color.setMinimumHeight(32)
    dialog.btn_bg_color.clicked.connect(dialog._pick_bg_color)

    dialog.checkbox_fill_bg.toggled.connect(dialog._on_fill_background_toggled)
    BACKGROUND.tag_member(dialog.checkbox_fill_bg, "export.fill_background")
    BACKGROUND.tag_member(dialog.btn_bg_color, "export.select_background_color")
    dialog.bg_color_row = QWidget()
    bg_row = QVBoxLayout(dialog.bg_color_row)
    bg_row.setContentsMargins(0, 0, 0, 0)
    bg_row.setSpacing(6)
    bg_row.addWidget(dialog.checkbox_fill_bg)
    bg_row.addWidget(dialog.btn_bg_color)
    dialog.current_bg_color = QColor(255, 255, 255, 255)


def build_metadata_block(dialog) -> None:
    dialog.checkbox_include_metadata = CheckBox(
        dialog._tr("export.include_metadata", "Include metadata")
    )
    dialog.checkbox_include_metadata.toggled.connect(
        dialog._on_include_metadata_toggled
    )
    ACTIONS.tag_member(dialog.checkbox_include_metadata, "export.include_metadata")

    dialog.comment_label = QLabel(dialog._tr("export.comment", "Comment") + ":")
    dialog.edit_comment = QLineEdit()
    dialog.checkbox_comment_default = CheckBox(
        dialog._tr("export.remember_by_default", "Remember by default")
    )


def build_action_bar(dialog) -> None:
    dialog.action_bar = DialogActionBar(
        dialog._tr("common.ok", "OK"),
        dialog._tr("common.cancel", "Cancel"),
        primary_min_size=(100, 36),
        secondary_min_size=(100, 36),
    )
    dialog.btn_ok = dialog.action_bar.primary_button
    dialog.btn_cancel = dialog.action_bar.secondary_button
    dialog.btn_ok.clicked.connect(dialog.accept)
    dialog.btn_cancel.clicked.connect(dialog.reject)
    ACTIONS.tag_member(dialog.btn_ok, "common.ok")
    ACTIONS.tag_member(dialog.btn_cancel, "common.cancel")


def assemble_export_form(dialog) -> tuple[QFrame, QFrame]:
    """Build preview + form panes and return ``(left_frame, right_frame)``."""
    left_frame = build_preview_pane(dialog)

    right_frame = QFrame()
    right_frame.setFrameShape(QFrame.Shape.NoFrame)
    dialog.export_form_frame = right_frame
    right_layout = QVBoxLayout(right_frame)
    right_layout.setContentsMargins(8, 8, 8, 8)
    # Base gap between stacked rows; extra height goes to addStretch slots.
    right_layout.setSpacing(8)

    build_output_path_section(dialog)
    build_format_row(dialog)
    build_resolution_row(dialog)
    build_quality_controls(dialog)
    build_png_options(dialog)
    build_background_row(dialog)
    build_metadata_block(dialog)
    build_action_bar(dialog)

    # Distribute extra height across section gaps (not one blob above OK).
    # Intra-section rows (label→field) stay tight via layout spacing only.
    right_layout.addWidget(dialog.output_section)
    # Fixed floor + shared stretch so filename→format never collapses to
    # the generic 8px row spacing.
    right_layout.addSpacing(export_geo.EXPORT_FILENAME_FORMAT_MIN_GAP_PX)
    right_layout.addStretch(1)
    right_layout.addWidget(dialog.fmt_label)
    right_layout.addWidget(dialog.combo_format)
    right_layout.addStretch(1)
    right_layout.addWidget(dialog.resolution_row)
    right_layout.addStretch(1)
    right_layout.addWidget(dialog.quality_row)
    right_layout.addStretch(1)
    right_layout.addWidget(dialog.png_row)
    right_layout.addStretch(1)
    right_layout.addWidget(dialog.bg_color_row)
    right_layout.addStretch(1)
    right_layout.addWidget(dialog.checkbox_include_metadata)
    right_layout.addWidget(dialog.comment_label)
    right_layout.addWidget(dialog.edit_comment)
    right_layout.addWidget(dialog.checkbox_comment_default)
    right_layout.addStretch(1)
    right_layout.addWidget(dialog.action_bar)

    return left_frame, right_frame


def assemble_export_ui(dialog) -> None:
    main_layout = QHBoxLayout(dialog)
    main_layout.setContentsMargins(12, 12, 12, 12)
    main_layout.setSpacing(12)

    left_frame, right_frame = assemble_export_form(dialog)
    main_layout.addWidget(left_frame, 1)
    main_layout.addWidget(right_frame, 0)

    dialog._on_include_metadata_toggled(dialog.checkbox_include_metadata.isChecked())
