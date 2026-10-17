"""P1 produce side — the metric profile is derived, stored and READ.

``plan-adaptive-metric-profiles-2026-10-17`` P1: the profile is the LIVE axis
set of the gallery state — derived from the folder's measured metrics when the
mode/metrics settle, stored on ``GalleryState.metric_profile``, read by the
rank fusion and the Jev vector. Without a stored profile every consumer keeps
behaving exactly as before (the mode mapping — fail-open).

Falsification stories (what each test would catch):

- ``refresh_metric_profile`` not storing anything, or deriving only the mode
  base (no salience): the stored profile of a scattered series must carry a
  ``salient_axes`` that the mode mapping does not imply;
- ``_apply_fusion_ranks`` IGNORING the stored profile (ranking from the mode
  mapping instead): a stored one-axis profile must invert the order a
  two-axis profile produces;
- ``clear_metric_profile`` not invalidating (the read seam keeping stale axes
  instead of falling back to the mode mapping);
- a raise/blank on garbage items/metrics (the derivation must fail open to a
  usable axis set);
- an unset default (``GalleryState().metric_profile`` must be ``None`` — the
  pre-P1 behaviour, so nothing changes for every existing consumer).

No Qt event loop, no torch/PIL, no network: a lightweight fake controller calls
the real (unbound) controller primitives over plain ``GalleryItem`` objects —
the same double ``tests/test_rank_wiring.py`` uses.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, GalleryState, Mode, Series
from tabs.image_gallery.services.metric_profile import (
    MetricProfile,
    profile_for_mode,
)
from tabs.image_gallery.use_cases.profile_select import active_profile


class _FakeController:
    """Minimal controller surface for the profile producer + rank primitive."""

    def __init__(self, items, series, mode=Mode.BATCH_SYNTHETIC) -> None:
        self.state = GalleryState(items=list(items), series=list(series), mode=mode)

    # -- bound delegations to the real controller primitives ----------------
    def refresh_metric_profile(self):
        return GalleryController.refresh_metric_profile(self)

    def clear_metric_profile(self):
        return GalleryController.clear_metric_profile(self)

    def _apply_fusion_ranks(self, series, *, mode=None):
        return GalleryController._apply_fusion_ranks(self, series, mode=mode)


def _item(name: str, **metrics) -> GalleryItem:
    it = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=0)
    it.metrics.update(metrics)
    return it


def _series(*items) -> list[Series]:
    return [Series(id="series_1", members=list(items))]


# --------------------------------------------------------------------------
# refresh stores a derived (salience-aware) profile on the state
# --------------------------------------------------------------------------


def test_refresh_stores_a_salience_aware_profile() -> None:
    # Two items differ only in ``ssim`` — a REFERENCE axis the
    # ``batch_synthetic`` mode base does NOT include, so a stored salient axis
    # proves the derivation went past the plain mode mapping.
    a = _item("a.png", ssim=1.0)
    b = _item("b.png", ssim=0.0)
    ctrl = _FakeController([a, b], _series(a, b), mode=Mode.BATCH_SYNTHETIC)
    assert ctrl.state.metric_profile is None  # pre-P1 default

    profile = ctrl.refresh_metric_profile()

    assert ctrl.state.metric_profile is profile
    assert profile.axis_ids, "a derived profile is always a usable axis set"
    assert set(profile.axis_ids) >= set(
        profile_for_mode(Mode.BATCH_SYNTHETIC).axis_ids
    ), "the mode base is always kept (fail-open)"
    assert "ssim" in profile.salient_axes
    assert "ssim" in profile.axis_ids


# --------------------------------------------------------------------------
# the rank reads the STORED profile, not just the mode mapping
# --------------------------------------------------------------------------


def test_apply_fusion_ranks_uses_the_stored_profile() -> None:
    # Two untagged axes, pulled in opposite directions:
    #   `a` is sharp but not clean (worst-axis cap limits its aggregate);
    #   `b` is clean but soft.
    a = _item("a.png", sharpness=400.0, noise=0.7)
    b = _item("b.png", sharpness=0.0, noise=0.0)
    ctrl = _FakeController([a, b], _series(a, b), mode=Mode.BATCH_SYNTHETIC)

    # No stored profile → the mode mapping (both axes measured) → `a` wins.
    ctrl._apply_fusion_ranks(ctrl.state.series, mode=ctrl.state.mode)
    assert (a.rank, b.rank) == (1, 2)

    # Store a profile restricted to the ONE axis where `b` wins → the fusion
    # order must INVERT; if the stored profile were ignored, nothing moves.
    ctrl.state.metric_profile = MetricProfile(axis_ids=("noise",))
    ctrl._apply_fusion_ranks(ctrl.state.series, mode=ctrl.state.mode)
    assert (b.rank, a.rank) == (1, 2)


# --------------------------------------------------------------------------
# clear invalidates → the read seam is back to the mode mapping
# --------------------------------------------------------------------------


def test_clear_invalidates_and_active_profile_falls_back() -> None:
    a = _item("a.png", sharpness=400.0)
    b = _item("b.png", sharpness=0.0)
    ctrl = _FakeController([a, b], _series(a, b), mode=Mode.CAMERA)

    ctrl.refresh_metric_profile()
    stored = ctrl.state.metric_profile
    assert stored is not None and stored.axis_ids
    assert active_profile(ctrl.state) is stored

    ctrl.clear_metric_profile()
    assert ctrl.state.metric_profile is None
    assert active_profile(ctrl.state).axis_ids == profile_for_mode(Mode.CAMERA).axis_ids


# --------------------------------------------------------------------------
# fail-open: garbage items/metrics never raise and always leave a profile
# --------------------------------------------------------------------------


def test_refresh_is_fail_open_on_garbage_input() -> None:
    ctrl = _FakeController([], [], mode=Mode.CAMERA)
    # Garbage item types AND garbage metric values.
    ctrl.state.items = [  # type: ignore[list-item]
        _item("x.png", sharpness="nope", noise=object()),
        None,
        "junk",
        3.5,
    ]

    profile = ctrl.refresh_metric_profile()  # must not raise

    assert profile.axis_ids, "a usable axis set is always produced"
    assert set(profile.axis_ids) >= set(profile_for_mode(Mode.CAMERA).axis_ids)
    assert active_profile(ctrl.state).axis_ids == tuple(profile.axis_ids)


# --------------------------------------------------------------------------
# the default is the pre-P1 behaviour
# --------------------------------------------------------------------------


def test_gallery_state_default_profile_is_none() -> None:
    assert GalleryState().metric_profile is None
