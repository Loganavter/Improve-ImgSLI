"""Video editor Standard tab layout: stretch pads + CRF row."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QSizePolicy, QVBoxLayout

from tabs.image_compare.plugins.video_editor.dialog.sections import (
    _sync_quality_stack_page,
    create_standard_export_tab,
)


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


def _tr_preset(preset: str) -> str:
    return preset


def test_standard_tab_distributes_equal_stretch_pads(qapp):
    dialog = SimpleNamespace(
        _tr=_tr,
        _tr_preset=_tr_preset,
        _settings_no_wheel_filter=None,
    )
    tab = create_standard_export_tab(dialog)
    from sli_ui_toolkit.widgets import OverlayScrollArea

    scroll = tab.findChild(OverlayScrollArea)
    assert scroll is not None
    content = scroll.widget()
    assert content is not None
    layout = content.layout()
    assert isinstance(layout, QVBoxLayout)

    stretch_slots = [
        i
        for i in range(layout.count())
        if layout.itemAt(i).spacerItem() is not None and layout.stretch(i) == 1
    ]
    # Between sections + trailing — not a single blob at the bottom.
    assert len(stretch_slots) >= 4
    assert content.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
    tab.deleteLater()


def test_quality_mode_and_value_are_stretch_separated(qapp):
    dialog = SimpleNamespace(
        _tr=_tr,
        _tr_preset=_tr_preset,
        _settings_no_wheel_filter=None,
    )
    tab = create_standard_export_tab(dialog)
    from sli_ui_toolkit.widgets import OverlayScrollArea

    content = tab.findChild(OverlayScrollArea).widget()
    layout = content.layout()
    assert isinstance(layout, QVBoxLayout)

    mode_idx = None
    stack_idx = None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        widget = item.widget() if item is not None else None
        if widget is dialog.quality_controls_container:
            mode_idx = i
        if widget is dialog.stack_quality:
            stack_idx = i
    assert mode_idx is not None and stack_idx is not None
    assert stack_idx > mode_idx
    # Equal stretch pad between quality mode and CRF/bitrate value.
    between = [
        i
        for i in range(mode_idx + 1, stack_idx)
        if layout.itemAt(i).spacerItem() is not None and layout.stretch(i) == 1
    ]
    assert between
    assert dialog.combo_quality_mode.parentWidget() is dialog.quality_controls_container
    assert dialog.stack_quality.parentWidget() is content
    tab.deleteLater()
