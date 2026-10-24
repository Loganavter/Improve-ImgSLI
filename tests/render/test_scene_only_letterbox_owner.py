"""The scene-only plan apply must not re-derive the letterbox.

Symptom this pins (plan-comparison-letterbox, measured on the D3D11 host
2026-10-24): in Image Compare the canvas aspect visibly changed between frames
with an unchanged label size and DPR 1.0 -- the log showed the letterbox
alternating ``0.837`` (envelope of the cropped tier, 1440x1056) and ``0.819``
(exactly the *preview* 1024x768 fit) inside the same canvas.

Cause: two writers of one geometry. The per-frame geometry pass owns the
letterbox and derives it from the drawn content (crop box applied); then
``apply_plan_scene_only`` re-ran ``update_common_letterbox_geometry`` with
``state._stored_pil_images`` -- the *preview* images, which carry no crop --
and overwrote it. Whichever wrote last won, so the aspect depended on the
tick order (invisible on a fast backend, visible on D3D11).

Contract: the owner is the single writer once a frame has a content rect;
``apply_plan_scene_only`` only *bootstraps* geometry (flows where nothing else
wrote it, e.g. a first scene-only apply).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.cache import display_tier_service as service


class _StoredImage:
    """Minimal duck-typed image: the preview the scene-only path used to read."""

    def __init__(self, width: int, height: int) -> None:
        self.width_value = width
        self.height_value = height

    def width(self) -> int:
        return self.width_value

    def height(self) -> int:
        return self.height_value

    @property
    def size(self):
        return (self.width_value, self.height_value)


def _state(content_rect):
    return SimpleNamespace(
        _stored_pil_images=[_StoredImage(1024, 768)],
        _shader_letterbox_mode=True,
        _content_rect_px=content_rect,
        _letterbox_params=[(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],
    )


def _hooks():
    tier = SimpleNamespace(
        resolve_slot_boxes=lambda *a, **k: (None, None),
        sanitize_box=lambda box, dims: box,
        box_dims=lambda box, dims: dims,
        dispatch_store_rect=lambda *a, **k: False,
    )
    steps = service.LegacyPlanSteps(
        resolve_clip_flag=lambda *a, **k: False,
        setup_store_bindings=lambda *a, **k: None,
        apply_overlays=lambda *a, **k: None,
    )
    return SimpleNamespace(tier=tier, steps=steps)


def _plan():
    return SimpleNamespace(
        preserve_zoom=True,
        geometry_letterbox=False,
        image_is_padded_composite=False,
        canvas_w=1512,
        canvas_h=929,
    )


def _run(monkeypatch, state, calls):
    monkeypatch.setattr(service, "update_common_letterbox_geometry", lambda *a, **k: calls.append(a))
    monkeypatch.setattr(service, "rebind_plan_store", lambda *a, **k: None)
    monkeypatch.setattr(service, "apply_plan_letterbox_from_clip", lambda *a, **k: None)
    monkeypatch.setattr(service, "capture_letterbox_focus", lambda *a, **k: None)
    monkeypatch.setattr(service, "restore_letterbox_focus", lambda *a, **k: None)
    canvas = SimpleNamespace(
        runtime_state=state,
        begin_update_batch=lambda: None,
        end_update_batch=lambda: None,
    )
    service.apply_plan_scene_only(
        canvas,
        _plan(),
        store=SimpleNamespace(),
        clip_overlays_to_image_bounds=False,
        hooks=_hooks(),
    )


def test_scene_only_apply_does_not_overwrite_owner_geometry(monkeypatch):
    """Red before the fix: a frame that already has a content rect gets rewritten.

    That rewrite is exactly the 0.837 -> 0.819 aspect jump (cropped tier
    envelope replaced by the preview fit).
    """
    calls: list = []
    _run(monkeypatch, _state((122, 0, 1266, 929)), calls)
    assert calls == [], (
        "apply_plan_scene_only re-derived the letterbox even though the frame "
        "already has a content rect -- this overwrites the owner's cropped "
        "envelope with the preview fit and makes the aspect jump "
        "(plan-comparison-letterbox)"
    )


def test_scene_only_apply_still_bootstraps_geometry(monkeypatch):
    """Flows where this pass is the only writer must keep working."""
    calls: list = []
    _run(monkeypatch, _state(None), calls)
    assert len(calls) == 1, (
        "scene-only apply must still bootstrap geometry when no content rect "
        "exists yet (export/video flows rely on it)"
    )


def test_zero_rect_counts_as_bootstrap(monkeypatch):
    """A (0,0,0,0) rect is 'nothing written yet', not 'written'."""
    calls: list = []
    _run(monkeypatch, _state((0, 0, 0, 0)), calls)
    assert len(calls) == 1


@pytest.mark.parametrize("rect", [None, (), (0, 0, 0, 0)])
def test_bootstrap_predicate_true_without_geometry(rect):
    assert service.geometry_needs_bootstrap(_state(rect)) is True


@pytest.mark.parametrize("rect", [(122, 0, 1266, 929), (1, 1, 1, 1)])
def test_bootstrap_predicate_false_once_written(rect):
    assert service.geometry_needs_bootstrap(_state(rect)) is False
