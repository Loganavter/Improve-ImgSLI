from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog

from plugins.video_editor.services.export_config import ExportConfigBuilder

class VideoEditorDialogExport:
    def __init__(self, dialog):
        self.dialog = dialog

    def get_export_options(self) -> dict:
        d = self.dialog
        is_manual = d.tabs.currentIndex() == 1
        output_opts = {"output_dir": d.edit_output_dir.text(), "file_name": d.edit_filename.text()}
        if is_manual:
            return {
                "manual_mode": True,
                "manual_args": d.edit_manual_args.text(),
                "fit_content_fill_color": d.fit_content_fill_color.name(QColor.NameFormat.HexArgb),
                **output_opts,
            }
        return {
            "manual_mode": False,
            "container": d.combo_container.currentData() or "mp4",
            "codec": ExportConfigBuilder.get_codec_internal_name(d.combo_codec.currentData() or "h264 (AVC)"),
            "quality_mode": d.combo_quality_mode.currentData() or "crf",
            "crf": int(d.edit_crf.text()) if d.edit_crf.text().isdigit() else 23,
            "bitrate": d.edit_bitrate.text(),
            "preset": d.combo_preset.currentData() or "",
            "pix_fmt": d.combo_pix_fmt.currentData() or "",
            "fit_content_fill_color": d.fit_content_fill_color.name(QColor.NameFormat.HexArgb),
            **output_opts,
        }

    def on_fit_fill_color_clicked(self):
        d = self.dialog
        color = QColorDialog.getColor(
            d.fit_content_fill_color,
            d,
            d._tr("export.select_background_color"),
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        d.fit_content_fill_color = color
        d._update_fit_fill_color_button()
        d.persistence.persist_export_settings()
        d.fitContentFillColorChanged.emit(color)

    def update_fit_fill_color_button(self):
        d = self.dialog
        if not hasattr(d, "btn_fit_fill_color"):
            return
        color = QColor(d.fit_content_fill_color)
        if not color.isValid():
            color = QColor(0, 0, 0, 255)
        if hasattr(d.btn_fit_fill_color, "set_color"):
            d.btn_fit_fill_color.set_color(color)

    def on_codec_changed(self, codec_text: str):
        d = self.dialog
        codec_name = d.combo_codec.currentData() or codec_text
        caps = ExportConfigBuilder.get_codec_capabilities(codec_name)
        current_quality_mode = d.combo_quality_mode.currentData()
        current_preset = d.combo_preset.currentData()
        current_pix_fmt = d.combo_pix_fmt.currentData()
        has_quality = caps["has_crf"] or caps.get("has_cq", False) or caps["has_bitrate"]
        d.quality_controls_container.setVisible(has_quality)
        if has_quality:
            d.combo_quality_mode.blockSignals(True)
            d.combo_quality_mode.clear()
            if caps["has_crf"]:
                d.combo_quality_mode.addItem(d._tr("video.crf_constant_quality"), "crf")
            if caps.get("has_cq", False):
                d.combo_quality_mode.addItem(d._tr(caps.get("cq_mode_label", "video.cq_constant_quality")), "cq")
            if caps["has_bitrate"]:
                d.combo_quality_mode.addItem(d._tr("video.bitrate_cbrvbr"), "bitrate")
            available_quality_modes = {
                d.combo_quality_mode.itemData(i) for i in range(d.combo_quality_mode.count())
            }
            if current_quality_mode in available_quality_modes:
                preferred_quality_mode = current_quality_mode
            elif caps.get("has_cq", False):
                preferred_quality_mode = "cq"
            elif caps["has_crf"]:
                preferred_quality_mode = "crf"
            else:
                preferred_quality_mode = "bitrate"
            quality_idx = d.combo_quality_mode.findData(preferred_quality_mode)
            d.combo_quality_mode.setCurrentIndex(max(0, quality_idx))
            d.combo_quality_mode.blockSignals(False)
            d.stack_quality.setCurrentIndex(d.combo_quality_mode.currentIndex())
            if hasattr(d, "lbl_quality_value"):
                quality_label = caps.get("quality_value_label", "video.crf_value_hint")
                if isinstance(quality_label, str) and "." in quality_label:
                    d.lbl_quality_value.setText(d._tr(quality_label) + ":")
                else:
                    d.lbl_quality_value.setText(str(quality_label) + ":")
        d.preset_container.setVisible(caps["has_preset"])
        if caps["has_preset"]:
            d.lbl_preset.setText(d._tr(caps.get("preset_label", "video.encoding_speed_preset")) + ":")
            d.combo_preset.blockSignals(True)
            d.combo_preset.clear()
            presets = ExportConfigBuilder.get_presets_for_codec(codec_name)
            for preset in presets:
                d.combo_preset.addItem(d._tr_preset(preset), preset)
            preferred_preset = current_preset
            if preferred_preset not in presets:
                preferred_preset = "medium" if "medium" in presets else ("standard" if "standard" in presets else (presets[0] if presets else ""))
            idx = d.combo_preset.findData(preferred_preset)
            if idx >= 0:
                d.combo_preset.setCurrentIndex(idx)
            elif presets:
                d.combo_preset.setCurrentIndex(0)
            d.combo_preset.blockSignals(False)
        else:
            d.combo_preset.clear()
        pix_fmts = ExportConfigBuilder.get_pixel_formats_for_codec(codec_name)
        d.pix_fmt_container.setVisible(bool(pix_fmts))
        d.combo_pix_fmt.blockSignals(True)
        d.combo_pix_fmt.clear()
        for pix_fmt in pix_fmts:
            d.combo_pix_fmt.addItem(pix_fmt, pix_fmt)
        preferred_pix_fmt = current_pix_fmt if current_pix_fmt in pix_fmts else ExportConfigBuilder.get_default_pixel_format_for_codec(codec_name)
        idx = d.combo_pix_fmt.findData(preferred_pix_fmt)
        if idx >= 0:
            d.combo_pix_fmt.setCurrentIndex(idx)
        elif pix_fmts:
            d.combo_pix_fmt.setCurrentIndex(0)
        d.combo_pix_fmt.blockSignals(False)
