"""Unify-gate reads the writer-side cache first.

Regression: the size-mismatch gate probed the Store-slot unify dict, which
no production writer fills (puts land in the controller PipelineCache), so
it always missed and forced a spurious preview hold over an already-cached
pair. The resolver prefers the controller cache, falls back to a thin
Store-slot wrapper, else None.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_compare.pipeline.cache import PipelineCache
from tabs.image_compare.presenters.image_canvas.background_parts.use_cases.bg_dirty import (
    _resolve_unify_gate_cache,
)


def _presenter(*, controller_cache=None, slot=None):
    controller = None
    if controller_cache is not None:
        controller = SimpleNamespace(pipeline=SimpleNamespace(cache=controller_cache))

    def _slot(name):
        assert name == "pipeline"
        if slot is None:
            raise AttributeError("no slot")
        return slot

    store = SimpleNamespace(get_session_state_slot=_slot)
    return SimpleNamespace(
        session_controller=controller,
        controller=None,
        main_window_app=None,
        widget=None,
        pipeline=None,
        store=store,
    )


def test_resolver_prefers_controller_cache():
    ctrl = PipelineCache()
    slot = SimpleNamespace(unify={}, preview={})
    resolved = _resolve_unify_gate_cache(_presenter(controller_cache=ctrl, slot=slot))
    assert resolved is ctrl


def test_resolver_falls_back_to_store_wrapper():
    slot = SimpleNamespace(unify={}, preview={})
    resolved = _resolve_unify_gate_cache(_presenter(slot=slot))
    assert resolved is not None
    assert resolved.get_unified(1, 2, "LANCZOS", 10, 10) is None


def test_resolver_none_when_nothing_reachable():
    assert _resolve_unify_gate_cache(_presenter()) is None
