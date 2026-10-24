"""Export defaults must consult QStandardPaths, not a hardcoded ``~/Downloads``.

The resolver ``default_downloads_dir`` lives in the image-compare export state;
every export default (still-image export state, video editor output field,
video editor browse dialog) must route through it. A fake ``QStandardPaths``
proves the call sites ask Qt for the location and that a redirected folder
(OneDrive) wins over ``~/Downloads``.

What this suite cannot prove: the path Qt actually answers on a real Windows
host (redirected or localised profile) — that needs a live host.

No ``QApplication`` is created here: ``QStandardPaths.writableLocation`` works
without one on the offscreen platform. If a platform ever requires an app
instance for it, this suite fails loudly instead of silently adding one.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QStandardPaths as _RealQStandardPaths

from tabs.image_compare.plugins.video_editor.dialog import persistence as persistence_module
from tabs.image_compare.plugins.video_editor.presenter_parts import common as common_module
from tabs.image_compare.plugins.video_editor.presenter_parts.output_paths import (
    OutputPathCoordinator,
)
from tabs.image_compare.services.image_export import state as state_module
from tabs.image_compare.services.image_export.state import (
    ExportStateCoordinator,
    default_downloads_dir,
)

_SOURCE_FILES = (
    Path(state_module.__file__),
    Path(common_module.__file__),
    Path(persistence_module.__file__),
)
_DOWNLOADS_LITERAL = 'Path.home() / "Downloads"'


def _fake_standard_paths(location: str):
    class _FakeQStandardPaths:
        StandardLocation = _RealQStandardPaths.StandardLocation

        @staticmethod
        def writableLocation(_kind):
            return location

    return _FakeQStandardPaths


@pytest.fixture
def redirected(tmp_path, monkeypatch):
    """Pretend the OS reports a redirected (OneDrive-style) Downloads folder."""
    target = tmp_path / "OneDrive" / "Downloads"
    target.mkdir(parents=True)
    monkeypatch.setattr(
        "PySide6.QtCore.QStandardPaths", _fake_standard_paths(str(target))
    )
    return target


class _LineEditStub:
    def __init__(self, text: str = ""):
        self._text = text

    def setText(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text

    def setCursorPosition(self, _position: int) -> None:
        pass


class _OutputPathCoordinatorProbe(OutputPathCoordinator):
    """Keeps only the output-dir defaulting logic of ``initialize_output_fields``."""

    def generate_suggested_name(self) -> str:
        return "video_export"

    def refresh_unique_output_filename(self) -> None:
        pass


def _output_path_coordinator(settings):
    view = SimpleNamespace(
        edit_output_dir=_LineEditStub(), edit_filename=_LineEditStub()
    )
    main_controller = SimpleNamespace(store=SimpleNamespace(settings=settings))
    editor_service = SimpleNamespace(get_snapshot_at_time=lambda _t: None)
    return _OutputPathCoordinatorProbe(
        view, main_controller, editor_service, SimpleNamespace()
    )


def _browse_dialog(settings):
    return SimpleNamespace(
        edit_output_dir=_LineEditStub(""),
        export_controller=SimpleNamespace(store=SimpleNamespace(settings=settings)),
        _tr=lambda key: key,
    )


def test_resolver_uses_redirected_standard_location(redirected):
    assert default_downloads_dir() == str(redirected.resolve())


def test_export_state_default_uses_redirected_standard_location(redirected):
    coordinator = ExportStateCoordinator(
        store=None, main_controller=None, main_window_app=None
    )
    assert coordinator.get_os_default_downloads() == str(redirected.resolve())

    # The dead ``_get_os_default_downloads`` probe must stay dead: an app object
    # exposing that attribute must not hijack the resolved location.
    legacy_app = SimpleNamespace(_get_os_default_downloads=lambda: "/legacy/wrong")
    legacy_coordinator = ExportStateCoordinator(
        store=None, main_controller=None, main_window_app=legacy_app
    )
    assert legacy_coordinator.get_os_default_downloads() == str(redirected.resolve())


def test_video_editor_output_dir_uses_redirected_standard_location(redirected):
    coordinator = _output_path_coordinator(
        SimpleNamespace(export_video_favorite_dir=None, export_default_dir="")
    )
    coordinator.initialize_output_fields()
    assert coordinator.view.edit_output_dir.text() == str(redirected.resolve())


def test_browse_output_dir_falls_back_to_redirected_standard_location(
    redirected, monkeypatch
):
    opened = {}

    class _FakeFileDialog:
        class Option:
            ShowDirsOnly = 1
            DontUseNativeDialog = 2

        @staticmethod
        def getExistingDirectory(_parent, _caption, directory, _options):
            opened["directory"] = directory
            return ""

    monkeypatch.setattr(persistence_module, "QFileDialog", _FakeFileDialog)
    persistence = persistence_module.VideoEditorDialogPersistence.__new__(
        persistence_module.VideoEditorDialogPersistence
    )
    persistence.dialog = _browse_dialog(
        SimpleNamespace(export_default_dir="")
    )

    persistence.browse_output_dir()

    assert opened["directory"] == str(redirected.resolve())


def test_empty_standard_location_falls_back_to_home_downloads(monkeypatch):
    monkeypatch.setattr("PySide6.QtCore.QStandardPaths", _fake_standard_paths(""))

    expected = str((Path.home() / "Downloads").resolve())
    result = default_downloads_dir()
    assert isinstance(result, str)
    assert result == expected
    assert common_module.default_downloads_dir() == expected
    assert (
        ExportStateCoordinator(None, None, None).get_os_default_downloads() == expected
    )


def test_missing_redirected_directory_returns_str_without_raising(
    tmp_path, monkeypatch
):
    target = tmp_path / "does" / "not" / "exist"
    monkeypatch.setattr(
        "PySide6.QtCore.QStandardPaths", _fake_standard_paths(str(target))
    )

    result = default_downloads_dir()

    assert isinstance(result, str)
    assert result.endswith("exist")


def test_home_downloads_location_keeps_existing_behaviour(monkeypatch):
    home_downloads = Path.home() / "Downloads"
    monkeypatch.setattr(
        "PySide6.QtCore.QStandardPaths", _fake_standard_paths(str(home_downloads))
    )

    expected = str(home_downloads.resolve())
    assert default_downloads_dir() == expected
    assert common_module.default_downloads_dir() == expected
    assert (
        ExportStateCoordinator(None, None, None).get_os_default_downloads() == expected
    )


def test_no_dead_probe_and_single_home_downloads_literal():
    sources = {
        path.name: path.read_text(encoding="utf-8") for path in _SOURCE_FILES
    }

    tree = ast.parse(sources["state.py"])
    probe_attributes = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "_get_os_default_downloads"
    ]
    probe_literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "_get_os_default_downloads"
    ]
    assert not probe_attributes, "the dead app-side hook must not be called"
    assert not probe_literals, "the dead hasattr probe must not survive"

    occurrences = sum(
        source.count(_DOWNLOADS_LITERAL) for source in sources.values()
    )
    assert occurrences == 1, (
        "the home Downloads literal must exist only as the resolver fallback; "
        f"found {occurrences}"
    )
    assert _DOWNLOADS_LITERAL in sources["state.py"]
    assert "QStandardPaths.StandardLocation.DownloadLocation" in sources["state.py"]
