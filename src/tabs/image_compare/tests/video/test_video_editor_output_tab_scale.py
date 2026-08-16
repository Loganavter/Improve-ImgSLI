"""Video editor Output tab buttons follow the UiScale factor (live + on open).

Regression: the output-path buttons were pinned with ``setFixedHeight(30)``
below the toolkit text-button content hint (~33 px at scale 1.0), clipping
the text at every factor; the pin was applied once at construction and never
re-applied on ``UiScale.scale_changed``, so increasing the interface scale
left the "вывод" tab buttons stuck at their old size.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.managers import UiScale, scaled_px
from sli_ui_toolkit.widgets import Button

from tabs.image_compare.plugins.video_editor.dialog.sections import create_output_tab
from ui.widgets.form_controls import OutputPathSection


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _make_dialog():
    return SimpleNamespace(
        _tr=_tr,
        _settings_no_wheel_filter=None,
        _browse_output_dir=lambda *a: None,
        _on_set_favorite_clicked=lambda *a: None,
        _on_use_favorite_clicked=lambda *a: None,
    )


def _output_buttons(dialog) -> list[Button]:
    return [
        dialog.btn_browse_output,
        dialog.btn_set_favorite,
        dialog.btn_use_favorite,
    ]


def test_output_tab_buttons_are_content_sized_not_fixed_clamped(qapp):
    dialog = _make_dialog()
    tab = create_output_tab(dialog)

    for button in (dialog.btn_browse_output, dialog.btn_set_favorite, dialog.btn_use_favorite):
        assert isinstance(button, Button)
        # No leftover fixed-height pin — the export dialog recipe drops it
        # because toolkit text buttons hint above any tight fixed height.
        assert button.maximumHeight() > 1000
        assert button.minimumHeight() >= scaled_px(32)
        assert button.height() >= button.sizeHint().height()
        assert button.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed

    tab.deleteLater()


def test_output_tab_buttons_scale_live(qapp):
    UiScale.get_instance().set_factor(1.0)
    dialog = _make_dialog()
    tab = create_output_tab(dialog)
    tab.show()
    qapp.processEvents()

    base_heights = [b.height() for b in _output_buttons(dialog)]
    assert all(h >= scaled_px(32) for h in base_heights)

    UiScale.get_instance().set_factor(2.0)
    qapp.processEvents()

    # Growth is the regression guard (the old fixed-height pin stayed
    # frozen); do not compare against sizeHint here — the app font can
    # differ across test files in the same process, which shifts hints.
    for button, base in zip(_output_buttons(dialog), base_heights):
        assert button.height() > base

    tab.deleteLater()


def test_output_path_section_repapplies_explicit_sizes_on_scale(qapp):
    UiScale.get_instance().set_factor(1.0)
    section = OutputPathSection(
        directory_label_text="Dir:",
        browse_text="Browse...",
        set_favorite_text="Set",
        use_favorite_text="Use",
        filename_label_text="File:",
        use_custom_line_edit=False,
        button_min_size=(40, 30),
        button_fixed_height=30,
    )
    section.show()
    qapp.processEvents()

    assert section.btn_browse_dir.maximumHeight() == 30

    UiScale.get_instance().set_factor(2.0)
    qapp.processEvents()

    # Re-applied with the live factor: 30 design px -> 60 logical px.
    assert section.btn_browse_dir.maximumHeight() == scaled_px(30) == 60
    assert section.btn_set_favorite.minimumWidth() == scaled_px(40) == 80

    section.deleteLater()
