"""ColorPickerDialog: hex alpha roundtrip, Enter-accept, recents row, i18n."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from resources.translations import tr
from sli_ui_toolkit.widgets import Label
from ui.widgets.color import ColorPickerDialog, RecentColorsStore


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def settings(tmp_path):
    return QSettings(os.path.join(str(tmp_path), "cfg.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def store(settings):
    return RecentColorsStore(settings)


def _show(dialog, qapp):
    dialog.show()
    qapp.processEvents()


def test_hex_display_respects_alpha_flag(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=True)
    try:
        assert dialog._hex_edit.text() == "#FF8800AA"
    finally:
        dialog.deleteLater()

    dialog = ColorPickerDialog(QColor(255, 136, 0, 255), show_alpha=True)
    try:
        assert dialog._hex_edit.text() == "#FF8800"
    finally:
        dialog.deleteLater()

    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=False)
    try:
        assert dialog._hex_edit.text() == "#FF8800"
    finally:
        dialog.deleteLater()


def test_hex_eight_digit_applies_alpha(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 255), show_alpha=True)
    try:
        dialog._hex_edit.setText("#FF8800AA")
        dialog._on_hex_edited()
        color = dialog.color()
        assert (color.red(), color.green(), color.blue(), color.alpha()) == (255, 136, 0, 170)
    finally:
        dialog.deleteLater()


def test_hex_six_digit_keeps_current_alpha(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=True)
    try:
        dialog._hex_edit.setText("#00FF00")
        dialog._on_hex_edited()
        color = dialog.color()
        assert (color.red(), color.green(), color.blue()) == (0, 255, 0)
        assert color.alpha() == 170
    finally:
        dialog.deleteLater()


def test_hex_eight_digit_ignored_without_alpha_flag(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 255), show_alpha=False)
    try:
        dialog._hex_edit.setText("#FF8800AA")
        dialog._on_hex_edited()
        color = dialog.color()
        assert (color.red(), color.green(), color.blue()) == (255, 136, 0)
        assert color.alpha() == 255
    finally:
        dialog.deleteLater()


def test_hex_invalid_restores_previous(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 255), show_alpha=True)
    try:
        dialog._hex_edit.setText("zzz")
        dialog._on_hex_edited()
        assert dialog._hex_edit.text() == "#FF8800"
    finally:
        dialog.deleteLater()


def test_enter_accepts_and_stores_recent(qapp, store):
    dialog = ColorPickerDialog(
        QColor(255, 136, 0, 170),
        show_alpha=True,
        recents_store=store,
    )
    selected = []
    dialog.colorSelected.connect(selected.append)
    try:
        _show(dialog, qapp)
        QTest.keyClick(dialog, Qt.Key.Key_Return)
        qapp.processEvents()
        assert dialog.result() == dialog.DialogCode.Accepted
        assert len(selected) == 1
        assert selected[0].alpha() == 170
        assert store.load() == ["#FF8800AA"]
    finally:
        dialog.deleteLater()


def test_recents_row_appears_after_first_accept(qapp, store):
    dialog = ColorPickerDialog(
        QColor("#224466"),
        recents_store=store,
    )
    try:
        assert not dialog._recents_row.isVisible()
        dialog._on_accept()
        assert store.load() == ["#224466"]
    finally:
        dialog.deleteLater()

    dialog2 = ColorPickerDialog(
        QColor("#224466"),
        recents_store=store,
    )
    try:
        assert not dialog2._recents_row.isHidden()
        assert len(dialog2._recents_row._chip_widgets) == 1  # 1 chip
    finally:
        dialog2.deleteLater()


def test_recents_row_shows_caption_section(qapp, store):
    store.add("#FF8800")
    dialog = ColorPickerDialog(
        QColor("#224466"),
        recents_store=store,
    )
    try:
        assert dialog._recents_row._caption.text() == tr("ui.recent_colors_caption", default="Recent")
        assert not dialog._recents_row._caption.isHidden()
        # Shelf structure: header host (title) + content host (chip grid).
        assert dialog._recents_row.root_layout().count() == 2
        assert len(dialog._recents_row._chip_widgets) == 1  # 1 chip in the store
    finally:
        dialog.deleteLater()


def test_fields_row_gaps_stable_and_right_aligned(qapp):
    dialog = ColorPickerDialog(QColor("#FF8800AA"), show_alpha=True)
    try:
        _show(dialog, qapp)
        dialog.resize(560, dialog.height())
        qapp.processEvents()
        gap_hex = dialog._hex_edit.x() - (dialog._preview.x() + dialog._preview.width())
        gap_r = dialog._r_spin.x() - (dialog._hex_edit.x() + dialog._hex_edit.width())
        for width in (560, 620, 680, 620, 560):
            dialog.resize(width, dialog.height())
            qapp.processEvents()
            # Anti-jitter: internal gaps never grow with dialog width.
            assert (
                dialog._hex_edit.x() - (dialog._preview.x() + dialog._preview.width())
            ) == gap_hex
            assert (
                dialog._r_spin.x() - (dialog._hex_edit.x() + dialog._hex_edit.width())
            ) == gap_r
            # Right-aligned: the group hugs the row's right edge.
            assert dialog._a_spin.x() + dialog._a_spin.width() == dialog.width() - 16
    finally:
        dialog.deleteLater()


def test_alpha_spin_syncs_and_respects_show_alpha(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=True)
    try:
        assert not dialog._a_spin.isHidden()
        assert not dialog._alpha_label.isHidden()
        assert dialog._a_spin.value() == 170
        # typing into the A spin updates the color
        dialog._a_spin.setValue(64)
        dialog._on_alpha_spin_changed(64)
        assert dialog.color().alpha() == 64
        # color changes resync the spin
        dialog.setCurrentColor(QColor(1, 2, 3, 200))
        assert dialog._a_spin.value() == 200
    finally:
        dialog.deleteLater()

    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=False)
    try:
        assert dialog._a_spin.isHidden()
        assert dialog._alpha_label.isHidden()
        assert not dialog._alpha_slider.isVisible()
    finally:
        dialog.deleteLater()


def test_recent_chip_applies_color_without_accepting(qapp, store):
    store.add("#FF8800AA")
    dialog = ColorPickerDialog(
        QColor("#224466"),
        show_alpha=True,
        recents_store=store,
    )
    selected = []
    dialog.colorSelected.connect(selected.append)
    try:
        _show(dialog, qapp)
        chip = dialog._recents_row._chip_widgets[0]
        QTest.mouseClick(chip, Qt.MouseButton.LeftButton)
        color = dialog.color()
        assert (color.red(), color.green(), color.blue(), color.alpha()) == (255, 136, 0, 170)
        assert dialog.result() != dialog.DialogCode.Accepted
        assert selected == []
    finally:
        dialog.deleteLater()


def test_ok_cancel_defaults_are_localized(qapp):
    dialog = ColorPickerDialog(QColor("#224466"))
    try:
        assert dialog._ok_text == tr("shared.common.ok", default="OK")
        assert dialog._cancel_text == tr("shared.common.cancel", default="Cancel")
    finally:
        dialog.deleteLater()


def test_field_labels_precede_each_input(qapp):
    dialog = ColorPickerDialog(QColor("#224466"), show_alpha=True)
    try:
        # No "Hex" label — the field is the cycle-format value input.
        assert [label.text() for label in dialog._field_labels] == ["R", "G", "B", "A"]
        root = dialog.layout()
        widgets = []
        for i in range(root.count()):
            item = root.itemAt(i)
            row = item.layout() if item is not None else None
            if row is None:
                continue
            row_widgets = []
            for j in range(row.count()):
                sub = row.itemAt(j)
                if sub is not None and sub.widget() is not None:
                    row_widgets.append(sub.widget())
            if dialog._hex_edit in row_widgets:
                widgets = row_widgets
                break
        texts = [w.text() for w in widgets if isinstance(w, Label)]
        assert texts == ["R", "G", "B", "A"]
        for expected, spin in zip(
            ("R", "G", "B", "A"),
            (dialog._r_spin, dialog._g_spin, dialog._b_spin, dialog._a_spin),
        ):
            idx = widgets.index(spin)
            assert widgets[idx - 1].text() == expected
    finally:
        dialog.deleteLater()


def test_explicit_ok_cancel_text_wins(qapp):
    dialog = ColorPickerDialog(QColor("#224466"), ok_text="Yes", cancel_text="No")
    try:
        assert dialog._ok_text == "Yes"
        assert dialog._cancel_text == "No"
    finally:
        dialog.deleteLater()


def test_format_button_cycles_value_format(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=True)
    try:
        button = dialog._format_btn
        assert button.region("_main").text == "HEX"
        assert dialog._hex_edit.text() == "#FF8800AA"

        dialog._on_format_btn_clicked()
        assert button.region("_main").text == "RGB"
        assert dialog._hex_edit.text() == "rgba(255, 136, 0, 170)"

        dialog._on_format_btn_clicked()
        assert button.region("_main").text == "HSL"
        assert dialog._hex_edit.text() == "hsla(32, 100%, 50%, 170)"

        dialog._on_format_btn_clicked()
        assert button.region("_main").text == "HEX"
        assert dialog._hex_edit.text() == "#FF8800AA"
    finally:
        dialog.deleteLater()


def test_value_field_edits_in_rgb_format(qapp):
    dialog = ColorPickerDialog(QColor("#224466"), show_alpha=True)
    try:
        dialog._on_format_btn_clicked()
        dialog._hex_edit.setText("rgba(10, 20, 30, 128)")
        dialog._on_hex_edited()
        color = dialog.color()
        assert (color.red(), color.green(), color.blue(), color.alpha()) == (10, 20, 30, 128)
        assert dialog._hex_edit.text() == "rgba(10, 20, 30, 128)"
    finally:
        dialog.deleteLater()


def test_value_field_edits_in_hsl_format_keeps_alpha_without_token(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=True)
    try:
        dialog._on_format_btn_clicked()  # RGB
        dialog._on_format_btn_clicked()  # HSL
        dialog._hex_edit.setText("hsl(210, 50%, 40%)")
        dialog._on_hex_edited()
        color = dialog.color()
        assert (color.red(), color.green(), color.blue()) == (51, 102, 153)
        assert color.alpha() == 170
    finally:
        dialog.deleteLater()


def test_value_field_invalid_input_restores_in_current_format(qapp):
    dialog = ColorPickerDialog(QColor(255, 136, 0, 170), show_alpha=True)
    try:
        dialog._on_format_btn_clicked()
        dialog._hex_edit.setText("zzz")
        dialog._on_hex_edited()
        assert dialog._hex_edit.text() == "rgba(255, 136, 0, 170)"
    finally:
        dialog.deleteLater()


def test_value_field_alpha_ignored_without_show_alpha(qapp):
    dialog = ColorPickerDialog(QColor("#224466"), show_alpha=False)
    try:
        dialog._on_format_btn_clicked()
        dialog._hex_edit.setText("rgba(10, 20, 30, 64)")
        dialog._on_hex_edited()
        assert dialog.color().alpha() == 255
        assert dialog._hex_edit.text() == "rgb(10, 20, 30)"
    finally:
        dialog.deleteLater()


def test_value_field_resyncs_on_color_change(qapp):
    dialog = ColorPickerDialog(QColor("#224466"))
    try:
        dialog._on_format_btn_clicked()
        dialog._on_format_btn_clicked()  # HSL
        dialog.setCurrentColor(QColor(255, 136, 0))
        assert dialog._hex_edit.text() == "hsl(32, 100%, 50%)"
    finally:
        dialog.deleteLater()