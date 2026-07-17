"""Host title bar menus (File / Help)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sli_ui_toolkit import TitleBarMenuStrip


def test_menu_controller_builds_file_and_help_menus(qapp):
    from types import SimpleNamespace

    from ui.main_window.menu_controller import MainWindowMenuController

    window = SimpleNamespace(
        windowTitle=lambda: "Improve ImgSLI",
        store=SimpleNamespace(settings=SimpleNamespace(current_language="en")),
        presenter=None,
    )
    controller = MainWindowMenuController(window)  # type: ignore[arg-type]
    strip = controller.build_menus()
    assert isinstance(strip, TitleBarMenuStrip)
    assert len(strip.buttons()) == 2
    assert strip.buttons()[0]._text == "File"
    assert strip.buttons()[0]._icon_unchecked is not None
    assert strip.buttons()[1]._text == "Help"


def test_startup_builds_title_bar_with_menu_strip(qapp):
    from PySide6.QtWidgets import QWidget

    from ui.main_window.startup import MainWindowStartupRuntime

    window = QWidget()
    window.store = type("S", (), {"settings": type("S2", (), {"current_language": "en"})()})()
    window._menu_controller = None
    runtime = MainWindowStartupRuntime(window)  # type: ignore[arg-type]
    bar = runtime._build_custom_title_bar()
    # App icon lives inside the File trigger, not as a separate leading label.
    assert bar._leading_host.layout().count() == 1
    assert bar._app_icon_label is None
    assert window._menu_controller is not None
    file_btn = window._menu_controller._menu_strip.buttons()[0]
    assert file_btn._icon_unchecked is not None
    assert file_btn.getGap() == TitleBarMenuStrip.GAP
    bar.deleteLater()
    window.deleteLater()
