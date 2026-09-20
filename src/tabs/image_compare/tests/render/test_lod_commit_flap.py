"""Flap diagnostic on LOD commit (plan-atomic-lod-transitions Wave B).

Pyramid readiness races oscillate raw keys A->B->A with quiet gaps that
defeat the settle window; the counter quantifies it for future hysteresis
work. Behavior unchanged: commit decisions identical with/without it.
"""

from types import SimpleNamespace
from unittest import mock

from tabs.image_compare.canvas.rhi_renderer.use_cases import lod_commit as lod_commit_module
from tabs.image_compare.canvas.rhi_renderer.use_cases.lod_commit import (
    commit_lod_keys,
)


def _renderer():
    return SimpleNamespace(
        _lod_pending_keys=None,
        _lod_pending_since=0.0,
        _lod_committed_keys=None,
        _lod_committed_source_ids=(None, None),
    )


def test_raw_oscillation_increments_flap_counter():
    renderer = _renderer()
    sources = (SimpleNamespace(), SimpleNamespace())
    base_image = SimpleNamespace()
    raws = [("a0", "a1"), ("b0", "b1"), ("a0", "a1")]
    with mock.patch.object(
        lod_commit_module, "resolve_lod_texture_keys", side_effect=raws
    ):
        commit_lod_keys(renderer, ("stored_0", "stored_1"), sources, base_image, (800, 600))
        assert renderer._lod_committed_keys == ("a0", "a1")
        assert getattr(renderer, "_lod_flap_count", 0) == 0
        commit_lod_keys(renderer, ("stored_0", "stored_1"), sources, base_image, (800, 600))
        assert getattr(renderer, "_lod_flap_count", 0) == 0
        commit_lod_keys(renderer, ("stored_0", "stored_1"), sources, base_image, (800, 600))
        assert renderer._lod_flap_count == 1
        # Commit behavior untouched: still holding first-seen through settle.
        assert renderer._lod_committed_keys == ("a0", "a1")


def test_steady_keys_never_count_flaps():
    renderer = _renderer()
    sources = (SimpleNamespace(), SimpleNamespace())
    base_image = SimpleNamespace()
    with mock.patch.object(
        lod_commit_module,
        "resolve_lod_texture_keys",
        return_value=("a0", "a1"),
    ):
        for _ in range(3):
            commit_lod_keys(renderer, ("stored_0", "stored_1"), sources, base_image, (800, 600))
    assert getattr(renderer, "_lod_flap_count", 0) == 0
