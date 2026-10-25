"""Early startup log: the window before ``setup_logging`` exists.

Why this is not just a logging test: ``main.entry``, the module imports, the
``QApplication`` hand-off and the RHI/D3D11 probe (307-374 ms cold) run before
``core.bootstrap._configure_logging`` attaches a handler. Logger lines from
that window are dropped by an unconfigured logger, and a windowed build points
``stderr`` at ``os.devnull`` -- the phase is invisible, not absent. Two probes
therefore run in **real subprocesses**:

* the real ``src/__main__.py`` module scope (its entry/import marks, no
  ``QApplication`` and no window) -- asserts ``main.entry`` is the first line
  at ~0 ms;
* an armed stall watchdog held off the event loop, proving a deliberate 400 ms
  block lands in the early file and not in ``log.txt``.

The in-process cases pin the gate (off by default: no file, no directory), the
per-run wipe, the bounded record, the silent failure on an unusable data dir,
and the switch back to the ordinary logger at ``ctx.logging_ready``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import core.stall_watch as sw
import core.startup_early_log as early
from core.log_names import APP_LOGGER_NAME, LEGACY_LOG_DIR_NAME
from core.startup_trace import early_log_path, early_mark, startup_mark

REPO = Path(__file__).resolve().parents[2]
_LINE_RE = re.compile(r"^\+\s*(?P<total>[0-9.]+)ms\s+\(\+\s*(?P<delta>[0-9.]+)ms\)\s+(?P<name>\S+)")

_FLAG_NAMES = (
    "IMGSLI_STARTUP_TRACE",
    "BLINKTABLE_STARTUP_TRACE",
    "IMGSLI_STALL_WATCH",
    "BLINKTABLE_STALL_WATCH",
    "IMGSLI_STARTUP_EARLY_SELFTEST_SLEEP_MS",
)


@pytest.fixture(autouse=True)
def _isolated_sink(monkeypatch, tmp_path):
    """Point the sink at a temp data dir and start each test with the flags off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    for name in _FLAG_NAMES:
        monkeypatch.delenv(name, raising=False)
    early._reload_for_tests()
    yield
    # Runs before monkeypatch restores the env: the process ends with the sink
    # off, so no later test inherits a path inside this test's tmp dir.
    early._reload_for_tests()


def _lines(path: str | None) -> list[str]:
    assert path is not None, "the early sink is off"
    return Path(path).read_text(encoding="utf-8").splitlines()


def _parse(line: str) -> tuple[float, float, str]:
    match = _LINE_RE.match(line)
    assert match, f"unparseable early-log line: {line!r}"
    return float(match.group("total")), float(match.group("delta")), match.group("name")


def test_directory_mirror_matches_the_toolkit():
    """The stdlib mirror of the toolkit's path convention cannot drift silently."""
    from sli_ui_toolkit.core.logging import get_log_directory

    for name in (APP_LOGGER_NAME, LEGACY_LOG_DIR_NAME):
        assert early._app_data_dir(name) == get_log_directory(name)


def test_default_off_touches_nothing(monkeypatch, tmp_path):
    """No flag -> no file, no directory, no mark (the default run is unchanged)."""
    assert early_log_path() is None
    assert early.debug_requested() is False
    early_mark("main.entry")
    startup_mark("ctx.begin")
    assert not list((tmp_path / "data").rglob(early.FILE_NAME))
    assert early_log_path() is None


def test_enabled_writes_entry_first_with_zero_delta(monkeypatch):
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    assert early._reload_for_tests() is not None

    early_mark("main.entry")
    early_mark("main.imports_done", modules=3)

    lines = _lines(early_log_path())
    total, delta, name = _parse(lines[0])
    assert name == "main.entry"
    # In-process the sink is rebuilt on demand, so "since this process started"
    # is the only honest offset; the +0 ms claim is pinned by the subprocess
    # probe below, where the sink is created at import time.
    assert total == delta
    second = lines[1]
    assert "main.imports_done" in second and "modules=3" in second


def test_stall_flag_alone_enables_the_sink(monkeypatch):
    """The watchdog flag is enough: its reports are the reason the file exists."""
    monkeypatch.setenv("IMGSLI_STALL_WATCH", "1")
    assert early._reload_for_tests() is not None
    assert early.debug_requested() is True


def test_file_is_wiped_per_traced_run(monkeypatch):
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    path = early._reload_for_tests()
    early_mark("main.entry")
    assert _lines(path)

    path = early._reload_for_tests()  # a second traced launch in-process
    assert Path(path).read_text(encoding="utf-8") == ""


def test_record_is_bounded(monkeypatch):
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    assert early._reload_for_tests() is not None
    early_mark("rhi.probe.end", effective="opengl", note="x" * 20_000)

    line = _lines(early_log_path())[0]
    assert len(line) <= early._MAX_RECORD_CHARS
    assert "effective=opengl" in line


def test_unusable_data_dir_disables_the_sink_silently(monkeypatch, tmp_path):
    """A file where the directory should be: no raise, sink simply off."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", str(blocker))
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")

    assert early._reload_for_tests() is None
    early_mark("main.entry")  # must not raise
    assert early_log_path() is None


def test_legacy_log_dir_is_used_until_migration_runs(monkeypatch, tmp_path):
    """Creating the new dir here would make log-dir migration say ``kept``.

    ``migrate_log_directory_once`` only aliases ``…/BlinkTable`` -> the legacy
    tree while the new directory is absent, so a traced run on an upgrade must
    not create it: the early file goes next to the user's existing ``log.txt``.
    """
    data = tmp_path / "data"
    legacy = data / LEGACY_LOG_DIR_NAME
    legacy.mkdir(parents=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")

    path = early._reload_for_tests()
    assert path == str(legacy / early.FILE_NAME)
    assert not (data / APP_LOGGER_NAME).exists()


def test_stall_report_goes_to_early_file_before_logging(monkeypatch, caplog):
    """Before ``ctx.logging_ready`` the watchdog writes to the file, not a dead logger."""
    import logging

    monkeypatch.setenv("IMGSLI_STALL_WATCH", "1")
    assert early._reload_for_tests() is not None
    assert early.logging_ready() is False
    caplog.set_level(logging.WARNING, logger=f"{APP_LOGGER_NAME}.stall_watch")

    assert early.write_record("[stall] gui-loop blocked 400ms; stack:") is True
    text = "\n".join(_lines(early_log_path()))
    assert "[stall] gui-loop blocked 400ms" in text
    assert not [r for r in caplog.records if "gui-loop blocked" in r.getMessage()]


def test_after_logging_ready_the_ordinary_log_owns_diagnostics(monkeypatch, caplog):
    import logging

    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    assert early._reload_for_tests() is not None
    caplog.set_level(logging.WARNING, logger=f"{APP_LOGGER_NAME}.stall_watch")

    startup_mark("ctx.logging_ready")  # emitted by bootstrap after setup_logging()
    assert early.logging_ready() is True

    sw._emit("[stall] after ready")
    assert [r for r in caplog.records if "after ready" in r.getMessage()]
    assert "after ready" not in "\n".join(_lines(early_log_path()))


def test_selftest_sleep_is_off_without_the_env(monkeypatch):
    monkeypatch.setenv("IMGSLI_STARTUP_TRACE", "1")
    early._reload_for_tests()
    assert early.selftest_sleep() == 0.0


def test_main_entry_emits_the_required_marks(monkeypatch):
    """The marks the task exists for must be emitted from ``main`` itself."""
    source = (REPO / "src" / "__main__.py").read_text(encoding="utf-8")
    for name in (
        "main.entry",
        "main.imports_done",
        "main.qapp_ready",
        "rhi.probe.start",
        "rhi.probe.end",
        "main.window_start",
        "main.window.init_done",
    ):
        assert f'"{name}"' in source, f"src/__main__.py no longer emits {name}"
    assert source.index('"main.entry"') < source.index('"main.imports_done"')
    assert "selftest_sleep" in source, "the deliberate-sleep hook is not wired into startup"


def _subprocess_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("IMGSLI_", "BLINKTABLE_"))
    }
    env.update(
        {
            "PYTHONPATH": str(REPO / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "QT_QPA_PLATFORM": "offscreen",
            "XDG_DATA_HOME": str(tmp_path / "data"),
        }
    )
    env.update(extra)
    return env


def test_real_main_module_marks_entry_at_zero_ms(tmp_path):
    """Narrow real process: ``__main__`` module scope only (no QApplication, no window)."""
    probe = tmp_path / "probe_main.py"
    probe.write_text(
        "import importlib.util, pathlib, sys\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "spec = importlib.util.spec_from_file_location('b5_probe_main', root / 'src' / '__main__.py')\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "from core.startup_trace import early_log_path\n"
        "print(early_log_path())\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(probe), str(REPO)],
        cwd=str(REPO),
        env=_subprocess_env(tmp_path, IMGSLI_STARTUP_TRACE="1", IMGSLI_STALL_WATCH="1"),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr

    path = result.stdout.strip().splitlines()[-1]
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    total, _delta, name = _parse(lines[0])
    assert name == "main.entry", f"first line must be main.entry, got {lines[0]!r}"
    assert total < 25.0, f"main.entry must be at ~0 ms, got +{total}ms"
    names = [_parse(line)[2] for line in lines]
    assert "main.imports_done" in names
    assert names.index("main.entry") < names.index("main.imports_done")
    assert Path(path).name == early.FILE_NAME
    assert Path(path).parent.name in (APP_LOGGER_NAME, LEGACY_LOG_DIR_NAME)


def test_deliberate_gui_block_lands_in_the_early_file(tmp_path):
    """400 ms sleep on the GUI thread, armed watchdog, logging never configured."""
    probe = tmp_path / "probe_stall.py"
    probe.write_text(
        "import sys, time\n"
        "from core.startup_trace import early_mark, early_log_path\n"
        "early_mark('main.entry')\n"
        "from PySide6.QtWidgets import QApplication\n"
        "app = QApplication([])\n"
        "early_mark('main.qapp_ready')\n"
        "from core.stall_watch import arm\n"
        "assert arm(tick_ms=10) is True\n"
        "from core.startup_early_log import selftest_sleep\n"
        "selftest_sleep()\n"  # the same hook src/__main__.py calls
        "time.sleep(0.5)\n"  # give the watchdog its tick; no event loop -> still blocked
        "print(early_log_path())\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(probe)],
        cwd=str(REPO),
        env=_subprocess_env(
            tmp_path,
            IMGSLI_STARTUP_TRACE="1",
            IMGSLI_STALL_WATCH="1",
            IMGSLI_STALL_THRESHOLD_MS="80",
            IMGSLI_STARTUP_EARLY_SELFTEST_SLEEP_MS="400",
        ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr

    path = Path(result.stdout.strip().splitlines()[-1])
    text = path.read_text(encoding="utf-8")
    assert "[stall] watchdog armed" in text, text
    assert "[stall] gui-loop blocked" in text, text
    assert "selftest_sleep" in text or "probe_stall" in text, (
        "the stall report must name the blocked frame, got:\n" + text
    )
    log_txt = path.parent / "log.txt"
    assert not log_txt.exists() or "[stall]" not in log_txt.read_text(
        encoding="utf-8", errors="replace"
    ), "nothing configured logging, so the stall must not reach log.txt"
