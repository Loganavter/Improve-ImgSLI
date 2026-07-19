"""Windows .imgsli ProgID helpers (unit-tested without real winreg)."""

from __future__ import annotations

from pathlib import Path

from services.system.windows_file_association import (
    EXTENSION,
    PROGID,
    association_is_current,
    open_command_for_exe,
    resolve_file_type_icon,
)


def test_open_command_quotes_exe_and_placeholder(tmp_path: Path):
    exe = tmp_path / "Improve_ImgSLI.exe"
    exe.write_bytes(b"MZ")
    assert open_command_for_exe(exe) == f'"{exe}" "%1"'


def test_resolve_file_type_icon_prefers_imgsli_ico_beside_exe(tmp_path: Path):
    exe = tmp_path / "Improve_ImgSLI.exe"
    exe.write_bytes(b"MZ")
    icons = tmp_path / "icons"
    icons.mkdir()
    target = icons / "imgsli-file.ico"
    target.write_bytes(b"ico")
    (icons / "icon.ico").write_bytes(b"app")
    found = resolve_file_type_icon(exe)
    assert found == target.resolve()


def test_association_is_current_false_when_open_key_missing(monkeypatch, tmp_path: Path):
    exe = tmp_path / "Improve_ImgSLI.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(
        "services.system.windows_file_association._is_windows",
        lambda: True,
    )

    class _Winreg:
        HKEY_CURRENT_USER = object()

        @staticmethod
        def OpenKey(*_args, **_kwargs):
            raise OSError("missing")

    import services.system.windows_file_association as mod

    monkeypatch.setitem(__import__("sys").modules, "winreg", _Winreg)
    # Re-bind import inside the function by calling after modules patch.
    assert association_is_current(exe=exe, icon=None) is False


def test_progid_constants():
    assert EXTENSION == ".imgsli"
    assert PROGID == "ImproveImgSLI.Project"
