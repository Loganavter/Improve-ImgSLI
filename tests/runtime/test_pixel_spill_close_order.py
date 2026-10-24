"""Spill close order: release the mapping, THEN unlink — or defer the unlink.

Why this exists: ``TiledPixelStore.close()`` used to just null its
``_memmap`` and call ``os.remove``. That relies on CPython refcounting:
``np.memmap`` shares one underlying mmap handle with every view of it, so
any surviving view (a tile slice, a shared-pixel registry view, a caller
holding the memmap) keeps the handle — and therefore the file — open. On
Windows an open handle turns ``os.remove`` into ``PermissionError``, which
the old ``close()`` swallowed at ``debug`` level: the ``.raw`` spill stayed
on disk forever. POSIX unlinks mapped files happily, which is why the leak
was invisible on Linux.

The new contract, asserted here:

- ``close()`` flushes and explicitly closes the mmap, then drops every
  reference it owns;
- if a reference survives (nothing was provably the last owner), the file
  is NOT unlinked and the path is recorded in the spill dir's
  ``.pending_spill_deletes`` journal, for the startup/purge sweep;
- if nothing survives, the file is removed immediately and no journal
  entry is left;
- the registry drops its own ``_Entry.memmap`` reference before the owning
  base closes, so the last base entry still deletes its spill at once
  instead of queueing it.

Single process, single store at a time: the tests drive the real spill
``QLockFile`` on ``tmp_path`` (same discipline as ``tests/render/test_spill_purge.py``)
and never run two stores concurrently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.store import shared_pixel_registry as spr
from engine.store import tiled_pixel_store as tps

_W, _H = 4, 4


@pytest.fixture
def spill_dir(tmp_path, monkeypatch):
    """Point the spill dir at ``tmp_path`` and hold the exclusive lock.

    Pre-seeding ``_spill_dir_cache`` keeps both the journal location and
    ``resolve_pixel_spill_dir()`` off the real Qt cache dir; acquiring the
    lock through the production entry point is what allows
    :func:`tps.sweep_pending_spill_deletes` to run at all.
    """
    monkeypatch.setattr(tps, "_spill_dir_cache", str(tmp_path))
    monkeypatch.setattr(tps, "_instance_lock", None)
    monkeypatch.setattr(tps, "_have_exclusive_lock", False)
    tps._acquire_instance_lock(str(tmp_path))
    assert tps._have_exclusive_lock is True
    yield tmp_path
    spr.clear()


def _allocate(spill_dir) -> tuple[tps.TiledPixelStore, Path]:
    store = tps.TiledPixelStore.allocate(_W, _H, tmp_dir=str(spill_dir))
    return store, Path(store.path)


def test_close_with_a_surviving_view_defers_the_unlink(spill_dir):
    store, spill = _allocate(spill_dir)
    assert spill.parent == spill_dir
    # A plain numpy view of the spill: same underlying mmap handle, exactly
    # like a tile slice or a shared registry view.
    view = store._memmap[0:2]

    store.close()

    # Red-before: on the unfixed code this assertion fails with
    # ``AssertionError: close() unlinked a spill a live view still maps``
    # because os.remove succeeds on POSIX regardless of the open mapping.
    assert spill.exists(), "close() unlinked a spill a live view still maps"
    assert tps.read_pending_spill_deletes() == [str(spill)]
    assert int(view.sum()) == 0  # survivor not invalidated by the release

    del view
    assert tps.sweep_pending_spill_deletes() == 1
    assert not spill.exists()
    assert tps.read_pending_spill_deletes() == []


def test_close_without_survivors_unlinks_immediately(spill_dir):
    store, spill = _allocate(spill_dir)

    store.close()

    assert not spill.exists()
    assert tps.read_pending_spill_deletes() == []
    assert tps.sweep_pending_spill_deletes() == 0


def test_purge_sweeps_the_deferred_journal(spill_dir):
    store, spill = _allocate(spill_dir)
    view = store._memmap[0:2]
    store.close()
    assert tps.read_pending_spill_deletes() == [str(spill)]

    del view
    reclaimed = tps.purge_stale_spill_files()
    tps.sweep_pending_spill_deletes()

    assert reclaimed == _W * _H * 4
    assert not spill.exists()
    assert tps.read_pending_spill_deletes() == []


def test_registry_last_entry_deletes_its_spill_immediately(spill_dir):
    store, spill = _allocate(spill_dir)
    handle = spr.publish(spill, store, crop_fingerprint=None)
    assert handle is not None
    assert spr.entry_count() == 1

    spr.release(handle)

    assert spr.entry_count() == 0
    assert not spill.exists(), (
        "the registry's own _Entry.memmap reference must not turn the last "
        "base close into a deferred delete"
    )
    assert tps.read_pending_spill_deletes() == []


def test_only_owned_spill_names_are_ever_queued(spill_dir):
    foreign = spill_dir / "not_a_spill.png"
    foreign.write_bytes(b"\0" * 8)

    assert tps.record_pending_spill_delete(str(foreign)) is False
    assert tps.read_pending_spill_deletes() == []
    assert foreign.exists()
