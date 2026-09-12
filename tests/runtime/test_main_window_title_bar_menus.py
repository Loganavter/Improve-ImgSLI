"""Host title bar menus (File / Help)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from tests.helpers.drain_until_stable import drain_until_stable


def test_project_start_path_uses_documents_and_localized_untitled(qapp, monkeypatch, tmp_path):
    from pathlib import Path

    from PySide6.QtCore import QStandardPaths

    from services.io.project_io import PROJECT_FILE_EXTENSION
    from ui.main_window.menu_controller import MainWindowMenuController

    docs = tmp_path / "Documents"
    docs.mkdir()
    monkeypatch.setattr(
        QStandardPaths,
        "writableLocation",
        lambda *_args, **_kwargs: str(docs),
    )

    class _FakeSettings:
        def value(self, key, default=""):
            return default

    window = SimpleNamespace(
        store=SimpleNamespace(
            settings=SimpleNamespace(current_language="ru"),
            get_active_workspace_session=lambda: SimpleNamespace(
                title="",
                session_type="session_picker",
            ),
        ),
        presenter=None,
    )
    controller = MainWindowMenuController(window)  # type: ignore[arg-type]
    pio = controller.project_io
    monkeypatch.setattr(pio, "project_settings", lambda: _FakeSettings())

    suggested = Path(pio.project_start_path(for_save=True))
    assert suggested.parent == docs
    assert suggested.name == f"Без названия{PROJECT_FILE_EXTENSION}"

    open_dir = pio.project_start_path(for_save=False)
    assert open_dir == str(docs)

    # Collision with an existing file → ``Name (1).imgsli`` like image export.
    (docs / f"Без названия{PROJECT_FILE_EXTENSION}").write_text("{}")
    suggested2 = Path(pio.project_start_path(for_save=True))
    assert suggested2.name == f"Без названия (1){PROJECT_FILE_EXTENSION}"

    # Store-side auto titles (canonical English) still fall back to Untitled.
    window.store.get_active_workspace_session = lambda: SimpleNamespace(
        title="Image Compare",
        session_type="image_compare",
    )
    suggested3 = Path(pio.project_start_path(for_save=True))
    assert suggested3.name == f"Без названия (1){PROJECT_FILE_EXTENSION}"

    # User-renamed tabs drive the suggested stem.
    window.store.get_active_workspace_session = lambda: SimpleNamespace(
        title="Мой проект",
        session_type="image_compare",
    )
    suggested_custom = Path(pio.project_start_path(for_save=True))
    assert suggested_custom.name == f"Мой проект{PROJECT_FILE_EXTENSION}"

    # Stale last-saved basename / Downloads must not poison a new unbound Save As.
    downloads = tmp_path / "Downloads"
    downloads.mkdir()

    class _LastPathSettings(_FakeSettings):
        def value(self, key, default=""):
            if key == "project_last_path":
                return str(downloads / f"My Custom Project{PROJECT_FILE_EXTENSION}")
            if key == "project_last_dir":
                return str(downloads)
            return default

    def _locations(location, *_args, **_kwargs):
        from PySide6.QtCore import QStandardPaths

        if location == QStandardPaths.StandardLocation.DocumentsLocation:
            return str(docs)
        if location == QStandardPaths.StandardLocation.DownloadLocation:
            return str(downloads)
        return str(docs)

    monkeypatch.setattr(QStandardPaths, "writableLocation", _locations)
    monkeypatch.setattr(pio, "project_settings", lambda: _LastPathSettings())
    pio.current_project_path = None
    window.store.get_active_workspace_session = lambda: SimpleNamespace(
        title="Image Compare",
        session_type="image_compare",
    )
    suggested4 = Path(pio.project_start_path(for_save=True))
    assert suggested4.parent == docs
    assert suggested4.name == f"Без названия (1){PROJECT_FILE_EXTENSION}"
    # Open falls back to Documents when last_dir was Downloads.
    assert pio.project_start_path(for_save=False) == str(docs)

    # Bound Save As keeps the file when the tab still matches the stem.
    bound = docs / f"My Custom Project{PROJECT_FILE_EXTENSION}"
    bound.write_text("{}")
    pio.current_project_path = str(bound)
    window.store.get_active_workspace_session = lambda: SimpleNamespace(
        title="My Custom Project",
        session_type="image_compare",
    )
    suggested5 = Path(pio.project_start_path(for_save=True))
    assert suggested5 == bound

    # Bound Save As follows a later tab rename.
    window.store.get_active_workspace_session = lambda: SimpleNamespace(
        title="Renamed Tab",
        session_type="image_compare",
    )
    suggested6 = Path(pio.project_start_path(for_save=True))
    assert suggested6.name == f"Renamed Tab{PROJECT_FILE_EXTENSION}"


def test_remember_project_path_renames_active_session(qapp, monkeypatch, tmp_path):
    from services.io.project_io import PROJECT_FILE_EXTENSION
    from ui.main_window.menu_controller import MainWindowMenuController

    session = SimpleNamespace(
        id="sess-1",
        title="Image Compare",
        session_type="image_compare",
    )
    renames: list[tuple[str, str]] = []

    class _FakeSettings:
        def value(self, key, default=""):
            return default

        def setValue(self, *_args, **_kwargs):
            return None

        def sync(self):
            return None

    window = SimpleNamespace(
        store=SimpleNamespace(
            settings=SimpleNamespace(current_language="en"),
            get_active_workspace_session=lambda: session,
            rename_workspace_session=lambda sid, title: renames.append((sid, title)),
        ),
        presenter=None,
    )
    controller = MainWindowMenuController(window)  # type: ignore[arg-type]
    pio = controller.project_io
    monkeypatch.setattr(pio, "project_settings", lambda: _FakeSettings())
    monkeypatch.setattr(pio, "refresh_session_picker_recent", lambda: None)
    monkeypatch.setattr(
        "services.io.recent_projects.record_recent_project",
        lambda *_a, **_k: None,
    )

    path = str(tmp_path / f"My Cool Project{PROJECT_FILE_EXTENSION}")
    pio.remember_project_path(path)
    assert renames == [("sess-1", "My Cool Project")]
    assert pio.current_project_path == path


def test_save_project_retargets_path_when_tab_renamed(qapp, monkeypatch, tmp_path):
    from pathlib import Path

    from services.io.project_io import PROJECT_FILE_EXTENSION
    from ui.main_window.menu_controller import MainWindowMenuController

    bound = tmp_path / f"Old Name{PROJECT_FILE_EXTENSION}"
    bound.write_text("{}")
    window = SimpleNamespace(
        store=SimpleNamespace(
            settings=SimpleNamespace(current_language="en"),
            get_active_workspace_session=lambda: SimpleNamespace(
                title="New Name",
                session_type="image_compare",
            ),
        ),
        presenter=None,
    )
    controller = MainWindowMenuController(window)  # type: ignore[arg-type]
    pio = controller.project_io
    pio.current_project_path = str(bound)
    writes: list[str] = []
    monkeypatch.setattr(pio, "write_project", lambda path: writes.append(path))

    controller._save_project()
    assert writes == [str(tmp_path / f"New Name{PROJECT_FILE_EXTENSION}")]


def test_menu_controller_builds_file_and_help_menus(qapp):
    from ui.main_window.csd_menu_strip import CsdMenuStrip
    from ui.main_window.menu_controller import MainWindowMenuController

    window = SimpleNamespace(
        windowTitle=lambda: "Improve ImgSLI",
        store=SimpleNamespace(settings=SimpleNamespace(current_language="en")),
        presenter=None,
    )
    controller = MainWindowMenuController(window)  # type: ignore[arg-type]
    strip = controller.build_menus()
    assert isinstance(strip, CsdMenuStrip)
    assert len(strip.buttons()) == 2
    assert strip.buttons()[0]._text == "File"
    assert strip.buttons()[0]._icon_unchecked is not None
    assert strip.buttons()[1]._text == "Help"

    file_entries = [
        entry
        for entry in controller._file_context_entries()
        if hasattr(entry, "action_id")
    ]
    by_id = {entry.action_id: entry for entry in file_entries}
    assert by_id["file.open_project"].shortcut == "Ctrl+Shift+O"
    assert by_id["file.save_project"].shortcut == "Shift+S"
    assert by_id["file.save_project_as"].shortcut == "Ctrl+Shift+S"
    assert by_id["file.new_session"].shortcut == "Ctrl+N"

    help_entries = [
        entry
        for entry in controller._help_context_entries()
        if hasattr(entry, "action_id")
    ]
    help_by_id = {entry.action_id: entry for entry in help_entries}
    assert help_by_id["help.find_action"].shortcut == "Ctrl+Shift+P"
    assert help_by_id["help.show"].shortcut == "Ctrl+F1"


def test_csd_menu_opens_as_in_window_overlay(qapp):
    """File/Help dropdowns are in-window SimpleOptionsFlyouts, not Qt.Popups."""
    from PySide6.QtCore import QEvent

    # conftest resets configure_toolkit per test; re-arm the overlay resolver
    # so the in-window flyout attaches to the host's OverlayLayer.
    from sli_ui_toolkit.config import configure_toolkit

    from shared_toolkit.ui.overlay_layer import OverlayLayer, get_overlay_layer
    from ui.main_window.menu_controller import MainWindowMenuController

    configure_toolkit(overlay_resolver=get_overlay_layer)

    host = QWidget()
    host.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    host.resize(500, 320)
    host.overlay_layer = OverlayLayer(host)
    host.store = SimpleNamespace(
        settings=SimpleNamespace(current_language="en"),
        get_dispatcher=lambda: SimpleNamespace(can_undo=lambda: False, can_redo=lambda: False),
        on_change=lambda _cb: None,
    )
    host.show()
    drain_until_stable(qapp, lambda: host.isVisible(), timeout_ms=1000, stable_frames=2)

    controller = MainWindowMenuController(host)  # type: ignore[arg-type]
    strip = controller.build_menus()
    host._menu_strip = strip
    strip.setParent(host)
    strip.show()
    drain_until_stable(qapp, lambda: strip.isVisible(), timeout_ms=1000, stable_frames=2)

    file_btn = strip.buttons()[0]
    try:
        row = strip.reveal_menu_action(file_btn, "file.open_project")
        drain_until_stable(qapp, lambda: strip._flyouts.get(id(file_btn)) is not None and strip._flyouts.get(id(file_btn)).isVisible(), timeout_ms=1000, stable_frames=2)
        assert row is not None

        flyout = strip._flyouts.get(id(file_btn))
        assert flyout is not None
        assert flyout.isVisible()
        assert not flyout.isWindow()
        assert flyout.window() is host
        assert flyout.overlay_layer is host.overlay_layer
        # Anchored below the CSD title bar area, inside the host window.
        assert flyout.y() >= file_btn.height()
        assert flyout.y() < host.height()
    finally:
        strip.hide()
        host.hide()
        host.close()
        host.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()


def test_save_project_falls_back_to_save_as_when_unsaved(qapp, monkeypatch):
    from ui.main_window.menu_controller import MainWindowMenuController

    window = SimpleNamespace(
        store=SimpleNamespace(settings=SimpleNamespace(current_language="en")),
        presenter=None,
    )
    controller = MainWindowMenuController(window)  # type: ignore[arg-type]
    pio = controller.project_io
    calls: list[str] = []
    monkeypatch.setattr(pio, "save_project_as", lambda: calls.append("as"))
    monkeypatch.setattr(
        pio, "write_project", lambda path: calls.append(f"write:{path}")
    )

    controller._save_project()
    assert calls == ["as"]

    pio.current_project_path = "/tmp/demo.imgsli"
    controller._save_project()
    assert calls == ["as", "write:/tmp/demo.imgsli"]


def test_startup_builds_title_bar_with_menu_strip(qapp):
    from ui.main_window.csd_menu_strip import CsdMenuStrip
    from ui.main_window.startup import MainWindowStartupRuntime

    window = QWidget()
    window.store = type("S", (), {"settings": type("S2", (), {"current_language": "en"})()})()
    window._menu_controller = None
    runtime = MainWindowStartupRuntime(window)  # type: ignore[arg-type]
    bar = runtime._build_custom_title_bar()
    # App icon lives inside the File trigger, not as a separate leading label;
    # the leading zone holds the menu strip plus the CSD undo/redo buttons.
    leading_widgets = [
        bar._leading_host.layout().itemAt(i).widget()
        for i in range(bar._leading_host.layout().count())
    ]
    assert isinstance(leading_widgets[0], CsdMenuStrip)
    assert leading_widgets[1] is window._menu_controller._undo_button
    assert leading_widgets[2] is window._menu_controller._redo_button
    assert bar._app_icon_label is None
    assert window._menu_controller is not None
    file_btn = window._menu_controller._menu_strip.buttons()[0]
    assert file_btn._icon_unchecked is not None
    assert file_btn.getGap() == CsdMenuStrip.GAP
    bar.deleteLater()
    window.deleteLater()


def test_language_change_rebuilds_strip_and_keeps_undo_redo_alive(qapp):
    """Regression: ``set_leading`` clears the whole leading zone (undo/redo
    included); the controller must reinstall them so a later store change
    cannot hit deleted C++ buttons (libshiboken RuntimeError)."""
    from shiboken6 import isValid

    from ui.main_window.csd_menu_strip import CsdMenuStrip
    from ui.main_window.startup import MainWindowStartupRuntime

    window = QWidget()
    window.store = type(
        "S", (), {"settings": type("S2", (), {"current_language": "en"})()}
    )()
    window._menu_controller = None
    runtime = MainWindowStartupRuntime(window)  # type: ignore[arg-type]
    bar = runtime._build_custom_title_bar()
    controller = window._menu_controller
    try:
        assert isValid(controller._undo_button)
        # Switch the store language so the rebuilt strip differs and the
        # early-return dedupe path is not taken.
        window.store.settings.current_language = "ru"
        controller._on_language_changed("ru")

        leading_widgets = [
            bar._leading_host.layout().itemAt(i).widget()
            for i in range(bar._leading_host.layout().count())
        ]
        assert isinstance(leading_widgets[0], CsdMenuStrip)
        # The buttons were wiped with the zone and reinstalled alive.
        assert isValid(controller._undo_button)
        assert isValid(controller._redo_button)
        assert leading_widgets[1] is controller._undo_button
        assert leading_widgets[2] is controller._redo_button
        # A store-change refresh must not raise on stale refs.
        controller._refresh_undo_redo_enabled()
    finally:
        bar.deleteLater()
        window.deleteLater()
        qapp.processEvents()


def test_csd_undo_redo_buttons_reflect_dispatcher_state(qapp):
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit import TitleBarPresets

    from ui.main_window.menu_controller import MainWindowMenuController

    state = {"can_undo": False, "can_redo": False}
    undos: list[str] = []
    redos: list[str] = []

    class _Disp:
        def can_undo(self):
            return state["can_undo"]

        def can_redo(self):
            return state["can_redo"]

        def undo(self):
            undos.append("u")

        def redo(self):
            redos.append("r")

    store = SimpleNamespace(
        settings=SimpleNamespace(current_language="en"),
        on_change=lambda cb: None,
        get_dispatcher=lambda: _Disp(),
    )
    window = QWidget()
    window.store = store
    controller = MainWindowMenuController(window)  # type: ignore[arg-type]
    bar = TitleBarPresets.app_shell(title="t", parent=window)
    try:
        controller._install_undo_redo_buttons(bar)

        assert controller._undo_button.isEnabled() is False
        assert controller._redo_button.isEnabled() is False

        state["can_undo"] = state["can_redo"] = True
        controller._refresh_undo_redo_enabled()
        assert controller._undo_button.isEnabled() is True
        assert controller._redo_button.isEnabled() is True

        controller._undo_button.click()
        controller._redo_button.click()
        assert undos == ["u"]
        assert redos == ["r"]

        state["can_undo"] = state["can_redo"] = False
        controller._refresh_undo_redo_enabled()
        assert controller._undo_button.isEnabled() is False
        assert controller._redo_button.isEnabled() is False
    finally:
        bar.deleteLater()
        window.deleteLater()
        qapp.processEvents()


def test_global_press_skips_flyout_close_on_title_bar_menu(qapp):
    """Press on File/Help must not arm the deferred outside-close (first-click race)."""
    """Press on File/Help must not arm the deferred outside-close (first-click race)."""
    from PySide6.QtCore import QEvent
    from ui.presenters.main_window import connections

    host = QWidget()
    try:
        host.resize(200, 80)
        host.show()
        trigger = QWidget(host)
        trigger.setObjectName("CsdMenuTrigger")
        trigger.setGeometry(10, 10, 60, 24)
        trigger.show()
        QApplication.processEvents()

        center = trigger.mapToGlobal(trigger.rect().center())
        assert connections._press_is_on_title_bar_menu(QPointF(center)) is True

        other = QWidget(host)
        other.setObjectName("SomethingElse")
        other.setGeometry(100, 10, 60, 24)
        other.show()
        QApplication.processEvents()
        other_center = other.mapToGlobal(other.rect().center())
        assert connections._press_is_on_title_bar_menu(QPointF(other_center)) is False

        presenter = SimpleNamespace(
            _popup_close_scheduled=False,
            ui_manager=SimpleNamespace(
                transient=SimpleNamespace(close_all_flyouts_if_needed=MagicMock())
            ),
        )
        press = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            QPointF(center),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        connections.handle_global_mouse_press(presenter, press)
        assert presenter._popup_close_scheduled is False

        press_other = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            QPointF(other_center),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        connections.handle_global_mouse_press(presenter, press_other)
        assert presenter._popup_close_scheduled is True
    finally:
        host.hide()
        host.close()
        host.deleteLater()
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        qapp.processEvents()