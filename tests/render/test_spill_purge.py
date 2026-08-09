"""purge_stale_spill_files must not be blocked by sentinels of dead PIDs.

Regression this guards: sentinel lock files from crashed/killed sessions
were treated as live, so purge bailed forever and stale multi-GB spill
files accumulated unboundedly in the cache dir (60 GB observed).
"""

from __future__ import annotations

import os

import pytest

from shared.image_processing import tiled_pixel_store as tps


@pytest.fixture
def spill_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tps, "_spill_dir_cache", str(tmp_path))
    monkeypatch.setattr(tps, "_pid_sentinel_path", None)
    return tmp_path


def _make_raw(spill_dir, name="imgsli_tps_stale.raw", size=1024):
    path = spill_dir / name
    path.write_bytes(b"\0" * size)
    return path


def test_stale_sentinel_does_not_block_purge(spill_dir):
    raw = _make_raw(spill_dir)
    dead_lock = spill_dir / "pid_999999999.lock"
    dead_lock.touch()

    reclaimed = tps.purge_stale_spill_files()

    assert reclaimed == 1024
    assert not raw.exists()
    assert not dead_lock.exists()


def test_live_foreign_sentinel_blocks_purge(spill_dir):
    raw = _make_raw(spill_dir)
    # PID 1 is always alive and never ours.
    live_lock = spill_dir / "pid_1.lock"
    live_lock.touch()

    reclaimed = tps.purge_stale_spill_files()

    assert reclaimed == 0
    assert raw.exists()
    assert live_lock.exists()


def test_own_sentinel_does_not_block_purge(spill_dir):
    raw = _make_raw(spill_dir)
    own_lock = spill_dir / f"pid_{os.getpid()}.lock"
    own_lock.touch()

    reclaimed = tps.purge_stale_spill_files()

    assert reclaimed == 1024
    assert not raw.exists()
    assert own_lock.exists()
