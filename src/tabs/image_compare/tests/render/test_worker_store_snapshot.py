"""WorkerStoreSnapshot must satisfy the Store API used by export workers.

Regression: still-image export crashed in the worker with
`AttributeError: 'WorkerStoreSnapshot' object has no attribute
'get_session_state_slot'` (`live_snapshot.build_live_frame_snapshot`,
`ExportService._get_current_display_name`) — the snapshot carried
`.document` but export code reads it via the Store accessor.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.store_settings import WorkerStoreSnapshot
from tabs.image_compare.services.live_snapshot import build_live_frame_snapshot


def _snapshot():
    document = SimpleNamespace(
        image1_path="a.png",
        image2_path="b.png",
        image_list1=[],
        image_list2=[],
        current_index1=0,
        current_index2=0,
        get_current_display_name=lambda n: f"name{n}",
    )
    return WorkerStoreSnapshot(
        viewport=SimpleNamespace(freeze_for_export=lambda: SimpleNamespace()),
        settings=SimpleNamespace(freeze_for_export=lambda: SimpleNamespace()),
        document=document,
    )


def test_snapshot_serves_document_slot():
    snap = _snapshot()
    assert snap.get_session_state_slot("document") is snap.document


def test_snapshot_rejects_unknown_slots_loudly():
    snap = _snapshot()
    with pytest.raises(KeyError):
        snap.get_session_state_slot("pipeline")


def test_build_live_frame_snapshot_accepts_worker_snapshot():
    """The exact production crash: export worker passes a snapshot."""
    snap = _snapshot()
    frame = build_live_frame_snapshot(snap)
    assert frame.image1_path == "a.png"
    assert frame.image2_path == "b.png"
    assert frame.name1 == "name1"
    assert frame.name2 == "name2"
