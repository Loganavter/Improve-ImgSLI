"""FontSettingsFlyout translations refresh with language."""

from __future__ import annotations

from PySide6.QtGui import QColor

from ui.widgets.font_settings_flyout import FontSettingsFlyout


def test_font_settings_flyout_retranslates_on_language(qapp, monkeypatch):
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    parent.show()

    strings = {
        ("label.font_size", "en"): "Font Size",
        ("label.font_size", "ru"): "Размер шрифта",
        ("label.bold", "en"): "Bold",
        ("label.bold", "ru"): "Жирный",
        ("label.opacity", "en"): "Opacity",
        ("label.opacity", "ru"): "Непрозрачность",
        ("label.color", "en"): "Color",
        ("label.color", "ru"): "Цвет",
        ("label.background", "en"): "Background",
        ("label.background", "ru"): "Фон",
        ("label.draw_text_background", "en"): "Draw background",
        ("label.draw_text_background", "ru"): "Рисовать фон",
        ("label.text_position", "en"): "Text Position",
        ("label.text_position", "ru"): "Позиция текста",
        ("label.position_edges", "en"): "Edges",
        ("label.position_edges", "ru"): "По краям",
        ("label.position_split_line", "en"): "Split line",
        ("label.position_split_line", "ru"): "На линии",
    }

    def fake_tr(key, lang="en", *_, **__):
        return strings.get((key, lang), key)

    monkeypatch.setattr("ui.widgets.font_settings_flyout.tr", fake_tr)

    flyout = FontSettingsFlyout(parent)
    try:
        assert flyout._size_label.text() == "Font Size"

        flyout.set_values(
            100,
            50,
            QColor("#fff"),
            QColor("#000"),
            True,
            "edges",
            100,
            "ru",
        )
        assert flyout._size_label.text() == "Размер шрифта"
        assert flyout._pos_radios["edges"].text() == "По краям"
        assert flyout._draw_bg_label.text() == "Рисовать фон"
    finally:
        flyout.hide()
        flyout.close()
        flyout.deleteLater()
        parent.hide()
        parent.close()
        parent.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()
