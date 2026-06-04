from __future__ import annotations

from resources.translations import tr
from sli_ui_toolkit.i18n import TranslationsBinder

from plugins.video_editor.services.export_config import ExportConfigBuilder


_PREVIEW_SCALE_ITEMS = (
    ("video.preview_quality_full", 1.0),
    ("video.preview_quality_balanced", 0.75),
    ("video.preview_quality_performance", 0.5),
    ("video.preview_quality_draft", 0.25),
)


def build_translations_binder(dialog) -> TranslationsBinder:
    """Build a TranslationsBinder for VideoEditorDialog."""
    binder = TranslationsBinder(tr_func=tr)

    binder.bind_callback(lambda lang: setattr(dialog, "current_language", lang or "en"))
    binder.bind_callback(
        lambda lang: dialog.setWindowTitle(tr("video.video_editor_exporter", lang))
    )

    _bind_labels(binder, dialog)
    _bind_buttons(binder, dialog)
    _bind_tabs(binder, dialog)
    _bind_output_section(binder, dialog)
    _bind_combo_rebuilds(binder, dialog)

    return binder


def _bind_labels(binder: TranslationsBinder, dialog) -> None:
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
        binder.bind_text(widget, key, suffix=":")
    binder.bind_text(dialog.lbl_manual_args_hint, "video.ffmpeg_output_args_hint")


def _bind_buttons(binder: TranslationsBinder, dialog) -> None:
    binder.bind_text(dialog.btn_export, "action.export_video")
    binder.bind_tooltip(dialog.btn_stop_export, "button.stop")
    binder.bind_tooltip(dialog.btn_lock_ratio, "video.lock_aspect_ratio")
    binder.bind_tooltip(dialog.btn_fit_content, "magnifier.fit_mode_toggle")
    binder.bind_tooltip(dialog.btn_fit_fill_color, "export.select_background_color")
    binder.bind_callback(
        lambda lang: dialog.btn_play.setToolTip(
            f"{tr('button.play', lang)} / {tr('button.pause', lang)}"
        )
    )
    binder.bind_tooltip(dialog.btn_undo, "button.undo_ctrlz")
    binder.bind_tooltip(dialog.btn_redo, "button.redo")
    binder.bind_tooltip(dialog.btn_trim, "button.trim_to_selection")


def _bind_tabs(binder: TranslationsBinder, dialog) -> None:
    tab_specs = (
        (dialog.tab_standard, "video.standard"),
        (dialog.tab_manual, "video.manual_cli"),
        (dialog.tab_output, "label.output"),
        (dialog.tab_log, "video.export_log"),
    )

    def _apply(lang: str) -> None:
        for tab, key in tab_specs:
            index = dialog.tabs.indexOf(tab)
            if index >= 0:
                dialog.tabs.setTabText(index, tr(key, lang))

    binder.bind_callback(_apply)


def _bind_output_section(binder: TranslationsBinder, dialog) -> None:
    binder.bind_text(
        dialog.output_section.dir_label,
        "export.select_output_directory",
        suffix=":",
    )
    binder.bind_text(dialog.btn_browse_output, "button.browse")
    binder.bind_text(dialog.btn_set_favorite, "misc.set_as_favorite")
    binder.bind_text(dialog.btn_use_favorite, "tooltip.use_favorite")
    binder.bind_text(dialog.output_section.filename_label, "label.file_name", suffix=":")


def _bind_combo_rebuilds(binder: TranslationsBinder, dialog) -> None:
    binder.bind_callback(lambda lang: _rebuild_preview_scale_combo(dialog, lang))
    binder.bind_callback(lambda lang: _rebuild_export_combos(dialog, lang))


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
    default_codec = ExportConfigBuilder.get_default_codec_for_container(current_container)
    dialog.update_available_codecs(codec_list, default_codec)
    codec_idx = dialog.combo_codec.findData(current_codec)
    if codec_idx >= 0:
        dialog.combo_codec.setCurrentIndex(codec_idx)

    dialog.export_ui.on_codec_changed(dialog.combo_codec.currentText())
