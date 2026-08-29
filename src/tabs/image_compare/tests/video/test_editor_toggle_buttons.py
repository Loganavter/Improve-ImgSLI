"""Video-editor resolution toolbar buttons — painter-owned toggle look.

Regression for the QSS retirement plan (Phase 3): ``editor.qss`` styled
``#btnLockRatio`` / ``#btnFitContent`` / ``#btnFitFillColor`` with
``background-color`` + ``:hover`` / ``:pressed`` / ``:checked`` state rules
that fought the toolkit painter. The QSS blocks were deleted; the buttons
now rely on the painter's default variant, whose ``button.toggle`` token
family must keep matching the retired QSS state table in both themes.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QPointF
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
from sli_ui_toolkit.managers import ThemeManager
from sli_ui_toolkit.ui.managers.theme_manager import ALIAS
from sli_ui_toolkit.ui.widgets.buttons.layers.background import (
    BgResolveParams,
    resolve_button_background,
)
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.buttons.variants import get_variant
from tabs.image_compare.plugins.video_editor.dialog.sections import (
    create_resolution_settings,
)

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


def _tm(theme: str) -> ThemeManager:
    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme(theme)
    return tm


def _build_buttons():
    dialog = SimpleNamespace(
        _tr=lambda key: key,
        _settings_no_wheel_filter=QObject(),
        _on_ratio_lock_toggled=lambda _checked: None,
        _on_fit_content_toggled=lambda _checked: None,
        _on_fit_fill_color_clicked=lambda: None,
        _on_width_edited=lambda: None,
        _on_height_edited=lambda: None,
    )
    create_resolution_settings(dialog)
    return (
        dialog.btn_lock_ratio,
        dialog.btn_fit_content,
        dialog.btn_fit_fill_color,
    )


def _resolved_last(btn, states, tm) -> QColor:
    layers, _border = resolve_button_background(
        BgResolveParams(states=frozenset(states), variant=get_variant(btn.getVariant())),
        tm,
    )
    assert layers, f"no background layers for states {states}"
    return layers[-1]


def _token_color(theme: str, key: str) -> QColor:
    """Palette value for a token key (following the toolkit ALIAS chain),
    without going through ThemeManager color getters."""
    palette = DARK_THEME_PALETTE if theme == "dark" else LIGHT_THEME_PALETTE
    cur = key
    for _ in range(len(ALIAS) + 1):
        if cur not in ALIAS:
            break
        cur = ALIAS[cur]
    return QColor(palette[cur])


# State set -> token key the retired QSS used for the same state.
_QSS_STATE_TOKENS = [
    ((), "button.toggle.background.normal"),
    ((ButtonState.HOVERED,), "button.toggle.background.hover"),
    ((ButtonState.PRESSED,), "button.toggle.background.pressed"),
    ((ButtonState.CHECKED,), "button.toggle.background.checked"),
    (
        (ButtonState.CHECKED, ButtonState.HOVERED),
        "button.toggle.background.checked.hover",
    ),
]


def test_editor_toggle_buttons_match_retired_qss_state_table():
    app = _app()
    for theme in ("light", "dark"):
        tm = _tm(theme)
        for btn in _build_buttons():
            app.processEvents()
            assert btn.getVariant() == "default"
            assert btn.getCornerRadiusPx() == 6
            for states, token in _QSS_STATE_TOKENS:
                assert _resolved_last(btn, states, tm) == _token_color(
                    theme, token
                ), f"{btn.objectName()} theme={theme} states={states}"


def test_editor_toggle_buttons_paint_qss_intended_background():
    app = _app()
    for theme in ("light", "dark"):
        tm = _tm(theme)
        for btn in _build_buttons():
            btn.show()
            app.processEvents()

            normal = _token_color(theme, "button.toggle.background.normal")
            hover = _token_color(theme, "button.toggle.background.hover")
            checked = _token_color(theme, "button.toggle.background.checked")
            checked_hover = _token_color(
                theme, "button.toggle.background.checked.hover"
            )
            center = QPointF(btn.width() / 2, btn.height() / 2)
            outside = QPointF(-1, -1)

            btn.setChecked(False)
            btn._update_hover_region(outside)
            assert _edge_pixel(btn) == normal

            btn._update_hover_region(center)
            assert _edge_pixel(btn) == hover
            btn._update_hover_region(outside)

            if btn._has_toggle:
                btn.setChecked(True)
                assert _edge_pixel(btn) == checked

                btn._update_hover_region(center)
                assert _edge_pixel(btn) == checked_hover
                btn._update_hover_region(outside)


def _edge_pixel(widget) -> QColor:
    img = widget.grab().toImage()
    return img.pixelColor(2, img.height() // 2)