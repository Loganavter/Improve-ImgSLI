"""One logger identity, one log directory, one spelling.

Three independent guarantees, all of them cheap enough to run in the fast tier:

* **identity** — the app logger is ``APP_LOGGER_NAME`` and nothing else; a
  logger fetched through the constant *is* ``logging.getLogger("BlinkTable")``
  (same object, not a same-named duplicate).
* **continuity** — ``migrate_log_directory_once`` aliases the pre-rename
  app-data directory so existing ``log.txt``/``trace.jsonl`` are not orphaned,
  and never deletes or overwrites anything, on any platform, under failure.
* **no second spelling** — no ``getLogger("ImproveImgSLI")`` literal survives
  anywhere under ``src/`` (source-text scan; a rename that misses 300 files
  would otherwise go unnoticed until a log line silently stops appearing).
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

import pytest

from core.log_dir_migration import migrate_log_directory_once
from core.log_names import (
    APP_LOGGER_NAME,
    APP_NAME,
    LEGACY_LOGGER_NAME,
    LEGACY_LOG_DIR_NAME,
)

# tests/runtime/test_log_identity.py -> <repo>/tests/runtime -> <repo>
SRC_ROOT = Path(__file__).resolve().parents[2] / "src"

#: Any call that still asks stdlib logging for the legacy logger id.
LEGACY_LOGGER_CALL = re.compile(r"getLogger\(\s*[\"']ImproveImgSLI")


def test_constant_names_the_blinktable_logger() -> None:
    assert APP_NAME == "BlinkTable"
    assert APP_LOGGER_NAME == "BlinkTable"

    # Same object, not merely the same name: a second ``getLogger`` call must
    # not create a parallel logger that misses the configured handlers.
    assert logging.getLogger(APP_LOGGER_NAME) is logging.getLogger("BlinkTable")


def test_legacy_names_stay_available_only_as_legacy() -> None:
    assert LEGACY_LOGGER_NAME == "ImproveImgSLI"
    assert LEGACY_LOG_DIR_NAME == "ImproveImgSLI"
    assert LEGACY_LOGGER_NAME != APP_LOGGER_NAME
    assert LEGACY_LOG_DIR_NAME != APP_LOGGER_NAME


@pytest.fixture()
def app_data(tmp_path, monkeypatch):
    """Point ``get_log_directory`` at a throwaway per-OS app-data root."""

    def _use(platform: str):
        monkeypatch.setattr(sys, "platform", platform)
        if platform == "win32":
            monkeypatch.setenv("APPDATA", str(tmp_path))
        else:
            monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        return tmp_path / "BlinkTable", tmp_path / "ImproveImgSLI"

    return _use


def _write_marker(directory: Path, name: str = "log.txt") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("old session\n", encoding="utf-8")
    return path


def test_migration_links_legacy_directory_on_posix(app_data) -> None:
    new_dir, old_dir = app_data("linux")
    marker = _write_marker(old_dir)

    assert migrate_log_directory_once() == "linked"
    assert new_dir.is_symlink()
    assert (new_dir / marker.name).read_text(encoding="utf-8") == "old session\n"
    # The legacy tree is aliased, never moved: a live process may hold it open.
    assert old_dir.is_dir() and marker.is_file()


def test_migration_renames_legacy_directory_on_windows(app_data) -> None:
    new_dir, old_dir = app_data("win32")
    _write_marker(old_dir)

    assert migrate_log_directory_once() == "renamed"
    # Copy-free: the old path is gone and the new one holds the same directory.
    assert not old_dir.exists()
    assert (new_dir / "log.txt").read_text(encoding="utf-8") == "old session\n"


def test_migration_keeps_existing_new_directory(app_data) -> None:
    new_dir, old_dir = app_data("linux")
    _write_marker(new_dir, "log.txt")
    _write_marker(old_dir, "log.txt")

    assert migrate_log_directory_once() == "kept"
    assert not new_dir.is_symlink()
    assert (new_dir / "log.txt").read_text(encoding="utf-8") == "old session\n"
    # Nothing was merged into or removed from either side.
    assert (old_dir / "log.txt").is_file()


def test_migration_does_nothing_when_neither_directory_exists(app_data) -> None:
    new_dir, old_dir = app_data("linux")

    assert migrate_log_directory_once() == "none"
    assert not os.path.lexists(new_dir)
    assert not old_dir.exists()


def test_migration_swallows_link_failure(app_data, monkeypatch) -> None:
    new_dir, old_dir = app_data("linux")
    _write_marker(old_dir)

    def _boom(*args, **kwargs):
        raise OSError("read-only data dir")

    monkeypatch.setattr(os, "symlink", _boom)

    # Never raises: a log-directory alias is a convenience, not a startup gate.
    assert migrate_log_directory_once() == "none"
    assert not os.path.lexists(new_dir)
    assert (old_dir / "log.txt").is_file()


def test_migration_drops_a_dangling_alias(app_data) -> None:
    """A symlink whose legacy target was deleted must not block logging.

    ``setup_logging`` cannot create a file behind a dead link (makedirs on the
    dangling path fails), so a stale alias would cost the process its log file
    on every start. The link carries no data — replacing it is safe.
    """
    new_dir, old_dir = app_data("linux")
    new_dir.symlink_to(old_dir, target_is_directory=True)
    assert os.path.lexists(new_dir) and not new_dir.exists()

    # Legacy directory gone too: the dead link is dropped and nothing is made.
    assert migrate_log_directory_once() == "none"
    assert not os.path.lexists(new_dir)

    # Legacy directory present: the alias is re-established.
    _write_marker(old_dir)
    assert migrate_log_directory_once() == "linked"
    assert (new_dir / "log.txt").read_text(encoding="utf-8") == "old session\n"


def test_no_legacy_logger_literal_under_src() -> None:
    assert SRC_ROOT.is_dir(), f"source root not found: {SRC_ROOT}"
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in LEGACY_LOGGER_CALL.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(SRC_ROOT.parent)}:{line}")
    assert not offenders, (
        "legacy logger id still requested under src/ (use APP_LOGGER_NAME):\n  "
        + "\n  ".join(offenders)
    )
