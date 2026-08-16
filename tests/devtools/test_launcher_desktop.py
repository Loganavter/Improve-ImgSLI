"""Desktop-integration tests for the launcher (tmp HOME, no real install).

Verifies idempotence (files byte-identical to build/linux sources), the
755 mode on the thumbnailer binary, template substitution for the
.desktop entry, and that cache-rebuild tools are only invoked when
something changed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import launcher

LINUX = sys.platform.startswith("linux")


def _quiet_ui():
    return launcher.UI(progress=False)


def _fake_home(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(launcher.Path, "home", classmethod(lambda cls: home))
    return home


def _bless_tool(monkeypatch):
    tool_calls = []

    def fake_run_tool(tool, args):
        tool_calls.append((tool, args))

    monkeypatch.setattr(launcher, "_run_tool", fake_run_tool)
    return tool_calls


def test_desktop_files_match_sources_byte_for_byte(monkeypatch, tmp_path):
    if not LINUX:
        return
    home = _fake_home(monkeypatch, tmp_path)
    _bless_tool(monkeypatch)

    assert launcher.desktop_integration(_quiet_ui(), mode="verbose")

    target = home / ".local" / "share" / "applications" / "improve-imgsli.desktop"
    assert target.is_file()
    template = launcher.DESKTOP_TEMPLATE.read_text(encoding="utf-8")
    expected = (
        template.replace("@LAUNCHER_PATH@", str(launcher.SCRIPT_DIR / "launcher.sh"))
        .replace("@ICON_PATH@", str(launcher.APP_ICON))
        .encode("utf-8")
    )
    assert target.read_bytes() == expected

    mime_dst = home / ".local" / "share" / "mime" / "packages" / "application-x-improve-imgsli.xml"
    assert mime_dst.is_file()
    assert mime_dst.read_bytes() == (launcher.DESKTOP_MIME_DIR / "application-x-improve-imgsli.xml").read_bytes()

    thumb_bin = home / ".local" / "bin" / "improve-imgsli-thumbnailer"
    assert thumb_bin.is_file()
    assert (thumb_bin.stat().st_mode & 0o777) == 0o755
    assert thumb_bin.read_bytes() == launcher.DESKTOP_THUMB_BIN.read_bytes()


def test_desktop_install_is_idempotent(monkeypatch, tmp_path):
    if not LINUX:
        return
    home = _fake_home(monkeypatch, tmp_path)
    tool_calls = _bless_tool(monkeypatch)

    assert launcher.desktop_integration(_quiet_ui(), mode="verbose")
    first_calls = len(tool_calls)
    assert first_calls > 0  # first install runs the cache rebuilds

    tool_calls.clear()
    assert launcher.desktop_integration(_quiet_ui(), mode="verbose")
    # verbose mode re-asserts the default handler; no cache rebuilds
    assert all(tool == "xdg-mime" for tool, _ in tool_calls)


def test_desktop_uninstall_removes_files(monkeypatch, tmp_path):
    if not LINUX:
        return
    home = _fake_home(monkeypatch, tmp_path)
    _bless_tool(monkeypatch)

    assert launcher.desktop_integration(_quiet_ui())
    target = home / ".local" / "share" / "applications" / "improve-imgsli.desktop"
    assert target.is_file()

    assert launcher.desktop_uninstall(_quiet_ui())
    assert not target.exists()
    assert not (home / ".local" / "share" / "mime" / "packages" / "application-x-improve-imgsli.xml").exists()
    assert not (home / ".local" / "bin" / "improve-imgsli-thumbnailer").exists()


def test_desktop_quiet_noop_off_linux(monkeypatch):
    if LINUX:
        return
    assert launcher.desktop_integration(_quiet_ui(), mode="verbose")
    assert launcher.desktop_uninstall(_quiet_ui())


def test_template_substitution_escapes_nothing(monkeypatch, tmp_path):
    """Path values are substituted literally (no regex/sed semantics)."""
    if not LINUX:
        return
    home = _fake_home(monkeypatch, tmp_path)
    _bless_tool(monkeypatch)
    launcher.desktop_integration(_quiet_ui())
    target = home / ".local" / "share" / "applications" / "improve-imgsli.desktop"
    text = target.read_text(encoding="utf-8")
    assert "@LAUNCHER_PATH@" not in text
    assert "@ICON_PATH@" not in text
    assert str(launcher.SCRIPT_DIR / "launcher.sh") in text
