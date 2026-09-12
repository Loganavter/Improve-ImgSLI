"""purge_stale_spill_files must not be permanently blocked by a lock left
behind by a dead/killed sibling process, but must still respect one that's
genuinely still running.

Regression this guards: the original scheme sentinel-filed each process's
PID under the spill dir and cross-checked it against ``/proc`` -- Linux
only, and if the background thread that ran the sweep never got scheduled
before a quick dev-cycle kill, dead sentinels could accumulate across many
sessions with nothing ever cleaning them up (60 GB observed). Replaced by
a single cross-platform ``QLockFile`` on the spill dir (Windows/macOS/Linux
all handled by one Qt implementation): its own stale-lock detection (PID +
hostname liveness) is what these tests exercise, via real child processes
so the liveness check is genuine rather than mocked.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from shared.image_processing import tiled_pixel_store as tps

_SRC_DIR = str(Path(tps.__file__).resolve().parents[2])

_CHILD_SCRIPT = """
import sys, os, time
sys.path.insert(0, {src!r})
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(["x", "-platform", "offscreen"])
import shared.image_processing.tiled_pixel_store as tps
tps._acquire_instance_lock({spill_dir!r})
print("LOCKED" if tps._have_exclusive_lock else "NOT_LOCKED", flush=True)
time.sleep({hold_seconds})
"""


def _spawn_lock_holder(spill_dir: str, hold_seconds: float) -> subprocess.Popen:
    """Starts a real child process that acquires the spill-dir lock and
    holds it for ``hold_seconds``. The caller decides whether to let it
    exit normally or SIGKILL it mid-sleep to simulate a crash."""
    script = _CHILD_SCRIPT.format(src=_SRC_DIR, spill_dir=spill_dir, hold_seconds=hold_seconds)
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline().strip()
    assert line == "LOCKED", f"child failed to acquire its own lock: {line!r} stderr={proc.stderr.read()}"
    return proc


@pytest.fixture
def spill_dir(tmp_path, monkeypatch):
    # Pre-seed the cache so resolve_pixel_spill_dir() (called inside
    # purge_stale_spill_files()) returns tmp_path without going through the
    # real QStandardPaths cache location. The lock itself is acquired
    # separately below/in the child script via _acquire_instance_lock,
    # which is the same step resolve_pixel_spill_dir() would otherwise take.
    monkeypatch.setattr(tps, "_spill_dir_cache", str(tmp_path))
    monkeypatch.setattr(tps, "_instance_lock", None)
    monkeypatch.setattr(tps, "_have_exclusive_lock", False)
    return tmp_path


def _make_raw(spill_dir, name="imgsli_tps_stale.raw", size=1024):
    path = spill_dir / name
    path.write_bytes(b"\0" * size)
    return path


def test_no_other_instance_purges_freely(spill_dir):
    raw = _make_raw(spill_dir)
    tps._acquire_instance_lock(str(spill_dir))

    reclaimed = tps.purge_stale_spill_files()

    assert reclaimed == 1024
    assert not raw.exists()
    assert tps._have_exclusive_lock is True


def test_dead_lock_holder_does_not_block_purge(spill_dir):
    raw = _make_raw(spill_dir)
    holder = _spawn_lock_holder(str(spill_dir), hold_seconds=30)
    try:
        # Simulate a crash / force-kill during dev iteration: the lock file
        # is left behind with a real, now-dead PID inside it instead of
        # being cleanly released.
        holder.send_signal(signal.SIGKILL)
        holder.wait(timeout=5)

        tps._acquire_instance_lock(str(spill_dir))
        reclaimed = tps.purge_stale_spill_files()

        assert reclaimed == 1024
        assert not raw.exists()
        assert tps._have_exclusive_lock is True
    finally:
        if holder.poll() is None:
            holder.kill()


def test_live_lock_holder_blocks_purge(spill_dir):
    raw = _make_raw(spill_dir)
    holder = _spawn_lock_holder(str(spill_dir), hold_seconds=5)
    try:
        tps._acquire_instance_lock(str(spill_dir))
        reclaimed = tps.purge_stale_spill_files()

        assert reclaimed == 0
        assert raw.exists()
        assert tps._have_exclusive_lock is False
    finally:
        holder.kill()
        holder.wait(timeout=5)