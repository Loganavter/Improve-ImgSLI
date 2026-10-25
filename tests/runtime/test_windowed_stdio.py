"""Windowed PyInstaller leaves sys.stderr as None; faulthandler must not crash.

relates_to: [src/core/windowed_stdio.py, src/core/startup_early_log.py]

The disabled-dump warning is a startup-position case: ``__main__`` arms the
opt-in fault dump *before* ``setup_logging`` attaches a handler, and a windowed
(``--noconsole``) build points ``stderr`` at ``os.devnull``. The one
"Fault dump disabled" line therefore has no visible sink unless it is written to
``startup_early.log`` -- the file the stall reports already use. The gate stays
intact: the default run (no ``IMGSLI_FAULT_DUMP``) still creates no directory and
no file, and an armed dump writes no warning at all.
"""

from __future__ import annotations

import faulthandler
import logging
import sys
from pathlib import Path

import pytest

import core.startup_early_log as early
import core.windowed_stdio as windowed
from core.log_names import APP_LOGGER_NAME
from core.windowed_stdio import enable_faulthandler, ensure_stdio

FAULT_DUMP_ENV = "IMGSLI_FAULT_DUMP"
FAULT_DUMP_FILE_ENV = "IMGSLI_FAULT_DUMP_FILE"
WARNING_PREFIX = "Fault dump disabled"

_DATA_FLAGS = (
    "IMGSLI_STARTUP_TRACE",
    "BLINKTABLE_STARTUP_TRACE",
    "IMGSLI_STALL_WATCH",
    "BLINKTABLE_STALL_WATCH",
)


@pytest.fixture
def early_sink(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Isolated app-data dir, both diagnostics flags off, fresh report flag."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    for name in _DATA_FLAGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(windowed, "_disabled_dump_reported", False)
    early._reload_for_tests()
    yield tmp_path / "data"
    # Restores the sink while the env monkeypatch is still active: no later test
    # inherits a path inside this test's tmp dir.
    early._reload_for_tests()


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


def _warning_lines(path: str | None) -> list[str]:
    assert path is not None, "the early sink is off, so the warning had no sink"
    text = Path(path).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if WARNING_PREFIX in line]


def test_faulthandler_raises_when_stderr_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stderr", None)
    with pytest.raises(RuntimeError, match="stderr is None"):
        faulthandler.enable()


def test_ensure_stdio_allows_faulthandler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", None)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    ensure_stdio()
    assert sys.stdin is not None
    assert sys.stdout is not None
    assert sys.stderr is not None

    enable_faulthandler()


# ---------------------------------------------------------------------------
# (a) a disabled dump reports exactly once, into the early file
# ---------------------------------------------------------------------------


def test_disabled_dump_writes_one_line_to_the_early_file(
    early_sink: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fault_dump_cleanup,
) -> None:
    """Opt-in dump + unwritable path: survival plus one record in the early file."""
    bad_path = early_sink / "absent" / "imgsli_fault_dump.log"
    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv(FAULT_DUMP_FILE_ENV, str(bad_path))
    caplog.set_level(logging.WARNING)

    enable_faulthandler()  # the whole point: returns normally

    path = early.path()
    lines = _warning_lines(path)
    assert len(lines) == 1, lines
    assert str(bad_path) in lines[0], lines[0]
    assert Path(path).parent.name == APP_LOGGER_NAME
    assert Path(path).parent.parent == early_sink
    # The ordinary logger still gets its line (it is just not visible in a
    # windowed build, which is why the file copy exists).
    assert [r for r in caplog.records if WARNING_PREFIX in r.getMessage()]


def test_repeated_calls_do_not_duplicate_the_line(
    early_sink: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_dump_cleanup,
) -> None:
    """``enable_faulthandler`` is re-armed (tests, retries): one record per process."""
    bad_path = early_sink / "absent" / "imgsli_fault_dump.log"
    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv(FAULT_DUMP_FILE_ENV, str(bad_path))

    enable_faulthandler()
    enable_faulthandler()
    enable_faulthandler()

    assert len(_warning_lines(early.path())) == 1, _warning_lines(early.path())


def test_traced_run_keeps_the_warning_next_to_its_marks(
    early_sink: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_dump_cleanup,
) -> None:
    """Traced + broken dump, sink already created: the mark stays first.

    Production order matters -- ``enable_faulthandler()`` runs before
    ``src/__main__.py`` imports ``core.startup_trace``, so the disabled-dump
    record is queued and flushed right after ``main.entry`` (see the module
    docstring); a later mark must not duplicate or wipe it.
    """
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    assert early._reload_for_tests() is not None

    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv(FAULT_DUMP_FILE_ENV, str(early_sink / "absent" / "dump.log"))
    enable_faulthandler()
    early.write_mark("main.entry")

    lines = Path(early.path()).read_text(encoding="utf-8").splitlines()
    assert any("main.entry" in line for line in lines[:1]), lines
    assert len([line for line in lines if WARNING_PREFIX in line]) == 1, lines
    assert lines.index(next(line for line in lines if WARNING_PREFIX in line)) == 1, lines


def test_traced_run_with_no_mark_yet_keeps_main_entry_first(
    early_sink: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_dump_cleanup,
) -> None:
    """The real order: the dump is armed BEFORE ``main.entry`` is written.

    ``src/__main__`` arms the fault dump at :31 and imports the trace module at
    :40, so a traced run with a broken dump reaches the warning with an empty
    file. The record must wait for the mark (every offset is relative to it) and
    then appear exactly once, right after it.
    """
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    assert early._reload_for_tests() is not None

    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv(FAULT_DUMP_FILE_ENV, str(early_sink / "absent" / "dump.log"))
    enable_faulthandler()

    assert _warning_lines(early.path()) == [], "the warning must not precede the mark"
    early.write_mark("main.entry")

    lines = Path(early.path()).read_text(encoding="utf-8").splitlines()
    assert "main.entry" in lines[0], lines
    assert len([line for line in lines if WARNING_PREFIX in line]) == 1, lines
    assert len([line for line in lines if WARNING_PREFIX in line]) == 1, lines


# ---------------------------------------------------------------------------
# (b) the default run is unchanged: no directory, no file
# ---------------------------------------------------------------------------


def test_default_run_still_touches_nothing(
    early_sink: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_dump_cleanup,
) -> None:
    monkeypatch.delenv(FAULT_DUMP_ENV, raising=False)
    monkeypatch.delenv(FAULT_DUMP_FILE_ENV, raising=False)

    enable_faulthandler()

    assert early.path() is None
    assert not early_sink.exists(), "the default run must not create the data dir"
    assert not list(early_sink.rglob(early.FILE_NAME))


def test_disabled_dump_with_no_usable_data_dir_still_returns(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    fault_dump_cleanup,
) -> None:
    """Both sinks unusable: the warning is dropped, startup still survives."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", str(blocker))
    for name in _DATA_FLAGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(windowed, "_disabled_dump_reported", False)
    assert early._reload_for_tests() is None
    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv(FAULT_DUMP_FILE_ENV, str(tmp_path / "absent" / "dump.log"))
    caplog.set_level(logging.WARNING)

    enable_faulthandler()

    assert early.path() is None
    assert [r for r in caplog.records if WARNING_PREFIX in r.getMessage()]
    early._reload_for_tests()


# ---------------------------------------------------------------------------
# (c) an armed dump writes no warning and no early file
# ---------------------------------------------------------------------------


def test_writable_dump_is_armed_and_writes_no_warning(
    early_sink: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    fault_dump_cleanup,
) -> None:
    dump = tmp_path / "custom-dump.log"
    monkeypatch.setenv(FAULT_DUMP_ENV, "1")
    monkeypatch.setenv(FAULT_DUMP_FILE_ENV, str(dump))
    caplog.set_level(logging.WARNING)

    enable_faulthandler()

    assert dump.is_file(), "the explicit path must still be armed verbatim"
    assert not [r for r in caplog.records if WARNING_PREFIX in r.getMessage()]
    assert early.path() is None, "an armed dump must not create the early file"
    assert not early_sink.exists()
