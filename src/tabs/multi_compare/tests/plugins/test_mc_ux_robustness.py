"""Multi Compare UX robustness: restore validation.

``deserialize_session`` skips malformed slot entries with a warning and
restores the well-formed rest — a corrupt entry (or an unknown version)
never aborts the session restore, so ``project_io``'s per-session loop
continues past bad sessions.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.use_cases import persistence as mc_persistence


class _SessionStore:
    def __init__(self):
        self.saved: dict = {}

    def set_session_state_slot(self, slot, state, *, session_id=None, emit_scope=None):
        self.saved[session_id] = state


def _restore(data) -> MultiCompareState:
    store = _SessionStore()
    context = SimpleNamespace(store=store)
    from tabs.multi_compare.tab import MultiCompareTab

    mc_persistence.deserialize_session(MultiCompareTab(), "s1", data, context)
    return store.saved["s1"]


def test_corrupt_slot_entries_restore_rest():
    """Malformed entries skip-and-log; well-formed siblings restore."""
    data = {
        "version": 1,
        "slots": [
            {"id": 1, "path": "/a.png", "label": "a"},
            {"bogus": True},
            {"id": "x", "path": "/bad.png"},
            {"id": 2, "path": 123},
            "not-a-dict",
            {"id": 3, "path": None, "label": "c"},
            {"id": 4, "path": "/d.png", "label": 7},
        ],
        "root": {"type": "leaf", "slot_id": 1},
        "zoom": "bad",
        # Legacy key from older builds: must be ignored, not rejected.
        "max_slots": 12,
    }
    state = _restore(data)
    assert [s.id for s in state.slots] == [1, 3, 4]
    assert state.slots[2].label == "7"
    assert state.zoom == 1.0


def test_unknown_version_still_restores_known_fields():
    """Forward-compat: version is read (and noted), known fields restore."""
    data = {
        "version": 99,
        "slots": [{"id": 1, "path": "/a.png", "label": "a"}],
        "root": "junk",
        "max_slots": 12,
    }
    state = _restore(data)
    assert [s.id for s in state.slots] == [1]
    assert state.root is None
