from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from tabs.image_gallery.tests.test_quicklook_strip import (
    _make_overlay,
    _real_png,
    _show,
    _strip_buttons,
)


def test_probe_real_strip_menu_stays(qtbot, tmp_path, monkeypatch):
    paths = [_real_png(tmp_path, f"p{i}.png") for i in range(3)]
    items = [GalleryItem(path=p, mtime_ns=i + 1) for i, p in enumerate(paths)]
    ov = _make_overlay(qtbot)
    _show(ov, items[0], items)
    QApplication.processEvents()

    from ui.context_menu import manager as _mgr_mod
    from ui.context_menu.manager import get_context_menu_manager

    hides = []
    mgr = get_context_menu_manager()
    real_hide = mgr.hide_active_menu

    def _hide():
        hides.append("hide_active_menu")
        return real_hide()

    monkeypatch.setattr(mgr, "hide_active_menu", _hide)

    target = None
    for b in _strip_buttons(ov):
        if b.property("gallery_path") == str(paths[2]):
            target = b
            break
    assert target is not None

    from PySide6.QtCore import Qt as _Qt
    from sli_ui_toolkit.widgets import ContextMenu as _CM

    qtbot.mouseClick(target, _Qt.MouseButton.RightButton)
    QApplication.processEvents()
    menus = [w for w in QApplication.topLevelWidgets() if isinstance(w, _CM)]
    print("AFTER CLICK menus:", menus, [m.isVisible() for m in menus])
    qtbot.wait(300)
    QApplication.processEvents()
    print("AFTER WAIT visible:", [m.isVisible() for m in menus])
    print("HIDES:", hides)
    print("ACTIVE:", get_context_menu_manager()._active_menu)
    ov.hide()
