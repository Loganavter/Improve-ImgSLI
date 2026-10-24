"""No hardcoded ``/tmp`` in the fault dump / perf trace defaults.

relates_to: [src/core/windowed_stdio.py, src/engine/frame/trace_export.py]

inv-windows-fs-correctness-2026-10-24, finding #7: ``/tmp`` always exists on
Linux, so two defaults that hardcoded it looked fine here and killed the app
on Windows —

- ``enable_faulthandler`` (``IMGSLI_FAULT_DUMP=1``) opened
  ``/tmp/imgsli_fault_dump.log`` unguarded from ``__main__`` *before* Qt, so a
  missing/read-only ``%TEMP%`` meant ``FileNotFoundError`` at startup;
- ``default_trace_path`` returned ``/tmp/imgsli-perf-trace-<pid>.json``, and
  ``write_trace`` propagates IO errors by contract, so ``IMGSLI_PERF_TRACE=1``
  raised inside the render loop.

Windows itself is not available offscreen, so these tests prove the portable
default the way the investigation asks: redirect ``tempfile.gettempdir()`` and
make the fault-dump open fail. What they cannot prove is a real Windows
``%TEMP%`` policy / ``HKCU\\Environment`` override — that is a live-proof item.
"""

from __future__ import annotations

import faulthandler
import logging
import os
import tempfile
from pathlib import Path

import pytest

from core.windowed_stdio import enable_faulthandler
from engine.frame.context import FrameContext
from engine.frame.trace_export import (
    PERF_TRACE_ENV,
    TRACE_PATH_ENV,
    default_trace_path,
    maybe_dump_trace,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

FAULT_DUMP_ENV = "IMGSLI_FAULT_DUMP"
FAULT_DUMP_FILE_ENV = "IMGSLI_FAULT_DUMP_FILE"


@pytest.fixture
def fault_dump_cleanup():
    """Undo the process-wide faulthandler state a test may have armed."""
    try:
        yield
    finally:
        faulthandler.cancel_dump_traceback_later()
        try:
            faulthandler.disable()
        except Exception:  # pragma: no cover - disable never raises in CPython
            pass


def _redirect_tempdir(monkeypatch: pytest.MonkeyPatch, directory: Path) -> Path:
    """``tempfile.gettempdir()`` -> ``directory`` (both modules call it live)."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(directory))
    return directory


# ---------------------------------------------------------------------------
# (a) fault dump default lands in the system temp dir
# ---------------------------------------------------------------------------


def test_fault_dump_default_lands_in_system_temp_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault_dump_cleanup,
) -> None:
    redirected = _redirect_tempdir(monkeypatch, tmp_path)
    monkeypatch.delenv(FAULT_DUMP_FILE_ENV, raising=False)
    monkeypatch.setenv(FAULT_DUMP_ENV, "1")

    enable_faulthandler()  # must not raise, must not touch the real /tmp

    dump = redirected / "imgsli_fault_dump.log"
    assert dump.is_file(), f"fault dump missing under redirected temp dir: {dump}"


def test_fault_dump_explicit_file_wins_verbatim(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault_dump_cleanup,
) -> None:
    _redirect_tempdir(monkeypatch, tmp_path / "ignored")
    explicit = tmp_path / "elsewhere" / "custom-dump.log"
    explicit.parent.mkdir()
    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv(FAULT_DUMP_FILE_ENV, str(explicit))

    enable_faulthandler()

    assert explicit.is_file(), "explicit IMGSLI_FAULT_DUMP_FILE must be used as-is"


# ---------------------------------------------------------------------------
# (b) an unusable fault-dump path disables the dump, never startup
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["directory", "missing-parent"])
def test_unopenable_fault_dump_is_disabled_with_one_warning(
    kind: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fault_dump_cleanup,
) -> None:
    if kind == "directory":
        # Windows: a dir where the log file should be -> IsADirectoryError.
        bad_path = tmp_path / "dump-is-a-directory"
        bad_path.mkdir()
    else:
        # The reported Windows failure mode: parent dir does not exist.
        bad_path = tmp_path / "absent" / "imgsli_fault_dump.log"
    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv(FAULT_DUMP_FILE_ENV, str(bad_path))
    caplog.set_level(logging.WARNING)

    enable_faulthandler()  # the whole point: returns normally

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    message = warnings[0].getMessage()
    assert str(bad_path) in message, message
    assert "disabled" in message.lower(), message


def test_fault_dump_interval_fallback_still_works(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fault_dump_cleanup,
) -> None:
    """A garbage interval falls back to 15 s instead of disabling the dump."""
    redirected = _redirect_tempdir(monkeypatch, tmp_path)
    monkeypatch.delenv(FAULT_DUMP_FILE_ENV, raising=False)
    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv("IMGSLI_FAULT_DUMP_INTERVAL", "not-a-number")

    enable_faulthandler()

    assert (redirected / "imgsli_fault_dump.log").is_file()


# ---------------------------------------------------------------------------
# (c) perf-trace default resolves through the system temp dir
# ---------------------------------------------------------------------------


def test_default_trace_path_uses_system_temp_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _redirect_tempdir(monkeypatch, tmp_path)
    monkeypatch.delenv(TRACE_PATH_ENV, raising=False)

    expected = tmp_path / f"imgsli-perf-trace-{os.getpid()}.json"
    assert default_trace_path() == str(expected)
    # pid suffix: two instances must never share a file.
    assert str(os.getpid()) in Path(default_trace_path()).name


def test_trace_path_override_wins_over_temp_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _redirect_tempdir(monkeypatch, tmp_path / "ignored")
    monkeypatch.setenv(TRACE_PATH_ENV, "/x/y.json")
    assert default_trace_path() == "/x/y.json"


def test_render_loop_dump_writes_into_system_temp_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``maybe_dump_trace`` with no explicit path follows the same default."""
    _redirect_tempdir(monkeypatch, tmp_path)
    monkeypatch.delenv(TRACE_PATH_ENV, raising=False)
    monkeypatch.setenv(PERF_TRACE_ENV, "1")

    ctx = FrameContext()
    assert maybe_dump_trace(ctx, every=1) > 0

    written = list(tmp_path.glob("imgsli-perf-trace-*.json"))
    assert [p.name for p in written] == [f"imgsli-perf-trace-{os.getpid()}.json"]


# ---------------------------------------------------------------------------
# (d) no ``/tmp`` literal left in either module
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative_path",
    ["src/core/windowed_stdio.py", "src/engine/frame/trace_export.py"],
)
def test_module_sources_have_no_tmp_literal(relative_path: str) -> None:
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert "/tmp" not in source, f"{relative_path} still hardcodes /tmp"
    assert "gettempdir" in source, f"{relative_path} must use tempfile.gettempdir()"
