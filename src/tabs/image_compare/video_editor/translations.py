from __future__ import annotations

from tabs.image_compare.video_editor.services.export_config import ExportConfigBuilder
from resources.translations import tr

_PREVIEW_SCALE_ITEMS = (
    ("video.preview_quality_full", 1.0),
    ("video.preview_quality_balanced", 0.75),
    ("video.preview_quality_performance", 0.5),
    ("video.preview_quality_draft", 0.25),
)


def apply_translations(dialog, lang: str) -> None:
    dialog.current_language = lang or "en"
    dialog.setWindowTitle(tr("video.video_editor_exporter", lang))
    _apply_labels(dialog, lang)
    _apply_buttons(dialog, lang)
    _apply_tabs(dialog, lang)
    _apply_output_section(dialog, lang)
    _rebuild_preview_scale_combo(dialog, lang)
    _rebuild_export_combos(dialog, lang)


def _apply_labels(dialog, lang: str) -> None:
    labels = (
        (dialog.lbl_resolution, "label.resolution"),
        (dialog.lbl_fps, "label.fps"),
        (dialog.lbl_preview_quality, "video.preview_quality"),
        (dialog.lbl_container, "label.container"),
        (dialog.lbl_video_codec, "label.video_codec"),
        (dialog.lbl_pix_fmt, "video.pixel_format"),
        (dialog.lbl_quality_control, "video.quality_control"),
        (dialog.lbl_quality_value, "video.crf_value_hint"),
        (dialog.lbl_preset, "video.encoding_speed_preset"),
        (dialog.lbl_bitrate, "video.bitrate_hint"),
    )
    for widget, key in labels:
        widget.setText(tr(key, lang) + ":")
    dialog.lbl_manual_args_hint.setText(tr("video.ffmpeg_output_args_hint", lang))


def _apply_buttons(dialog, lang: str) -> None:
    dialog.btn_export.setText(tr("action.export_video", lang))
    dialog.btn_stop_export.setToolTip(tr("button.stop", lang))
    dialog.btn_lock_ratio.setToolTip(tr("video.lock_aspect_ratio", lang))
    dialog.btn_fit_content.setToolTip(tr("magnifier.fit_mode_toggle", lang))
    dialog.btn_fit_fill_color.setToolTip(tr("export.select_background_color", lang))
    dialog.btn_play.setToolTip(
        f"{tr('button.play', lang)} / {tr('button.pause', lang)}"
    )
    dialog.btn_undo.setToolTip(tr("button.undo_ctrlz", lang))
    dialog.btn_redo.setToolTip(tr("button.redo", lang))
    dialog.btn_trim.setToolTip(tr("button.trim_to_selection", lang))


def _apply_tabs(dialog, lang: str) -> None:
    tab_specs = (
        (dialog.tab_standard, "video.standard"),
        (dialog.tab_manual, "video.manual_cli"),
        (dialog.tab_output, "label.output"),
        (dialog.tab_log, "video.export_log"),
    )

    for tab, key in tab_specs:
        index = dialog.tabs.indexOf(tab)
        if index >= 0:
            dialog.tabs.setTabText(index, tr(key, lang))


def _apply_output_section(dialog, lang: str) -> None:
    dialog.output_section.dir_label.setText(
        tr("export.select_output_directory", lang) + ":"
    )
    dialog.btn_browse_output.setText(tr("button.browse", lang))
    dialog.btn_set_favorite.setText(tr("misc.set_as_favorite", lang))
    dialog.btn_use_favorite.setText(tr("tooltip.use_favorite", lang))
    dialog.output_section.filename_label.setText(tr("label.file_name", lang) + ":")


def _rebuild_preview_scale_combo(dialog, lang: str) -> None:
    current = dialog.combo_preview_scale.currentData()
    dialog.combo_preview_scale.blockSignals(True)
    dialog.combo_preview_scale.clear()
    for key, value in _PREVIEW_SCALE_ITEMS:
        dialog.combo_preview_scale.addItem(tr(key, lang), value)
    idx = dialog.combo_preview_scale.findData(current)
    dialog.combo_preview_scale.setCurrentIndex(max(0, idx))
    dialog.combo_preview_scale.blockSignals(False)


def _rebuild_export_combos(dialog, lang: str) -> None:
    current_container = dialog.combo_container.currentData() or "mp4"
    current_codec = dialog.combo_codec.currentData()

    dialog.combo_container.blockSignals(True)
    dialog.combo_container.clear()
    for container in ExportConfigBuilder.get_available_containers():
        dialog.combo_container.addItem(tr(container, lang), container)
    container_idx = dialog.combo_container.findData(current_container)
    dialog.combo_container.setCurrentIndex(max(0, container_idx))
    dialog.combo_container.blockSignals(False)

    codec_list = ExportConfigBuilder.get_codecs_for_container(current_container)
    default_codec = ExportConfigBuilder.get_default_codec_for_container(
        current_container
    )
    dialog.update_available_codecs(codec_list, default_codec)
    codec_idx = dialog.combo_codec.findData(current_codec)
    if codec_idx >= 0:
        dialog.combo_codec.setCurrentIndex(codec_idx)

    dialog.export_ui.on_codec_changed(dialog.combo_codec.currentText())
