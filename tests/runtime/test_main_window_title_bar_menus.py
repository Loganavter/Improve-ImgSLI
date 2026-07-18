"""Host title bar menus (File / Help)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit import TitleBarMenuStrip


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


def test_global_press_skips_flyout_close_on_title_bar_menu(qapp):
    """Press on File/Help must not arm the deferred outside-close (first-click race)."""
    from ui.presenters.main_window import connections

    host = QWidget()
    host.resize(200, 80)
    host.show()
    trigger = QWidget(host)
    trigger.setObjectName("TitleBarMenuTrigger")
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

    host.deleteLater()
