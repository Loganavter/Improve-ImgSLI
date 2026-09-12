"""Video editor scroll surfaces use the toolkit SurfaceScrollArea."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.widgets import SurfaceScrollArea

from tabs.image_compare.plugins.video_editor.dialog.sections import (
    _wrap_tab_scroll,
    create_timeline_scroll_area,
)


def test_tab_scroll_uses_surface_scroll_area_transparent_mode(qapp):
    """Tab panes already paint their surface — scroll area must not add one."""
    content = QWidget()
    tab = _wrap_tab_scroll(content)
    scroll = tab.findChild(SurfaceScrollArea)
    assert scroll is not None
    assert scroll.widget() is content
    assert scroll._surface_token is None
    tab.deleteLater()


def test_timeline_scroll_uses_surface_scroll_area_token_mode(qapp):
    dialog = SimpleNamespace(_on_head_moved=lambda *a: None, _on_trim_clicked=lambda *a: None)
    scroll = create_timeline_scroll_area(dialog)
    try:
        assert isinstance(scroll, SurfaceScrollArea)
        assert scroll._surface_token == "surface.background"
        assert scroll.minimumHeight() > 0
        assert dialog.timeline is not None
        assert scroll.widget() is dialog.timeline
    finally:
        scroll.deleteLater()