"""P4 — named metric domains, the manual override and its analysis seam.

Falsification story (what each test would catch):

- a domain that is a second axis vocabulary: every domain profile must be a
  subset of ``MEASURED_POOL`` in registry order, and ``auto`` must be exactly
  ``profile_for_mode`` (the type is reused, never forked);
- a stats-driven domain choice that ignores the measurements (a folder whose
  only moving axis is ``brisque`` must not be labelled with the mode's domain
  when the evidence says otherwise), or that flips with dict/table order;
- an override that dies with the ``state`` object on a pool rebuild (the whole
  point of P4: the pick is a controller-level decision);
- an override that leaks into the next folder ("auto" must restore the mode
  profile, not keep the previous pin);
- an override that never reaches the analysis path: ``ActionContext`` must
  carry the pinned profile as ``ctx.profile`` (the analyzer reads the context,
  not ``state``), and the VLM selector must not silently replace a manual pick.

Pure-python fakes only (no Qt event loop, no torch/PIL, no network).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryState, Mode
from tabs.image_gallery.services.metric_profile import (
    DOMAIN_WEIGHTS,
    DOMAINS,
    MEASURED_POOL,
    MetricProfile,
    domain_for_mode,
    domain_for_stats,
    profile_for_domain,
    profile_for_mode,
)
from tabs.image_gallery.use_cases.action_context import build_context


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics=dict(metrics))


class _FakeController:
    """The real unbound controller primitives over one replaceable state."""

    _folder_gen = 0

    def __init__(self, items, mode=Mode.CAMERA) -> None:
        self.state = GalleryState(items=list(items), mode=mode)
        self._metric_domain = ""
        # Duck-typed widget without a stats strip: publishing must fail open.
        self.widget = SimpleNamespace()

    def refresh_metric_profile(self):
        return GalleryController.refresh_metric_profile(self)

    def set_metric_domain(self, domain):
        return GalleryController.set_metric_domain(self, domain)

    def restore_metric_profile(self):
        return GalleryController.restore_metric_profile(self)

    def clear_metric_profile(self):
        return GalleryController.clear_metric_profile(self)

    def _is_current_folder_gen(self, gen: int) -> bool:
        return int(gen) == self._folder_gen

    def _apply_profile_outcome(self, profile, gen: int):
        return GalleryController._apply_profile_outcome(self, profile, gen)


# --------------------------------------------------------------------------
# the named-domain table over the measured pool
# --------------------------------------------------------------------------


def test_named_domains_are_pool_subsets_in_registry_order():
    for domain in DOMAINS:
        profile = profile_for_domain(domain, mode=Mode.CAMERA)
        assert isinstance(profile, MetricProfile)
        assert profile.domain == domain
        assert profile.axis_ids, f"{domain} must imply at least one axis"
        assert set(profile.axis_ids) <= set(MEASURED_POOL)
        # Registry order is the value object's canonical order.
        assert list(profile.axis_ids) == [
            axis for axis in MEASURED_POOL if axis in profile.axis_ids
        ]
        # Every weighted axis is a real pool axis (no fabricated vocabulary).
        for axis_id in DOMAIN_WEIGHTS[domain]:
            assert axis_id in MEASURED_POOL


def test_auto_is_the_mode_mapping_and_unknown_domains_fall_back_to_it():
    for mode in (Mode.FIDELITY, Mode.CAMERA, Mode.BATCH_SYNTHETIC, None):
        auto = profile_for_domain("auto", mode=mode)
        assert auto == profile_for_mode(mode)
        assert auto.domain == ""
        # Unknown/empty values normalize to auto — fail-open, never a crash.
        for value in ("", None, "telepathy", object()):
            assert profile_for_domain(value, mode=mode) == profile_for_mode(mode)


def test_profile_for_domain_filters_to_the_given_pool():
    restricted = profile_for_domain(
        "photo", pool=("sharpness", "noise"), mode=Mode.CAMERA
    )
    assert restricted.axis_ids == ("sharpness", "noise")
    # No overlap with the available pool → empty domain profile, so the
    # consumer falls back to the mode mapping (fail-open).
    assert profile_for_domain("photo", pool=(), mode=Mode.CAMERA) == profile_for_mode(
        Mode.CAMERA
    )


# --------------------------------------------------------------------------
# the stats-driven domain choice
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spreads", "mode", "expected"),
    [
        # One decisive axis from a domain's own table.
        ({"sharpness": 60.0}, Mode.CAMERA, "document"),
        ({"brisque": 40.0}, Mode.CAMERA, "photo"),
        ({"lpips": 40.0}, Mode.BATCH_SYNTHETIC, "synthetic"),
        # Broad, evenly distributed spread → no domain dominates.
        (
            {
                "sharpness": 30.0,
                "exposure": 30.0,
                "clipping": 30.0,
                "noise": 30.0,
                "white_balance": 30.0,
                "aesthetic": 30.0,
                "brisque": 30.0,
            },
            Mode.CAMERA,
            "mixed",
        ),
        # No usable signal → the mode's domain (always answerable).
        ({}, Mode.FIDELITY, "document"),
        ({}, Mode.CAMERA, "photo"),
        ({}, Mode.BATCH_SYNTHETIC, "synthetic"),
        ({}, None, "mixed"),
    ],
)
def test_domain_for_stats_follows_the_axes_that_move(spreads, mode, expected):
    assert domain_for_stats(spreads=spreads, mode=mode) == expected


def test_domain_for_stats_reads_items_and_never_raises():
    a = _item("a.png", sharpness=0.0)
    b = _item("b.png", sharpness=400.0)
    assert domain_for_stats([a, b], mode=Mode.CAMERA) == "document"
    # Single item / garbage / missing metrics must not invent a signal.
    for items in ([a], None, 3, "nope", [None, object()]):
        assert domain_for_stats(items, mode=Mode.CAMERA) in DOMAINS


def test_domain_for_mode_maps_the_three_modes_and_defaults_to_mixed():
    assert domain_for_mode(Mode.FIDELITY) == "document"
    assert domain_for_mode(Mode.CAMERA) == "photo"
    assert domain_for_mode(Mode.BATCH_SYNTHETIC) == "synthetic"
    assert domain_for_mode(None) == "mixed"


# --------------------------------------------------------------------------
# manual override: persists across a rebuild, clears to the mode profile
# --------------------------------------------------------------------------


def test_override_survives_a_state_rebuild():
    items = [_item("a.png", sharpness=100.0), _item("b.png", sharpness=120.0)]
    ctrl = _FakeController(items, mode=Mode.CAMERA)

    picked = ctrl.set_metric_domain("document")

    assert picked.domain == "document"
    assert ctrl.state.metric_profile == picked
    assert ctrl.state.metric_domain == "document"
    assert set(picked.axis_ids) == set(profile_for_domain("document").axis_ids)

    # A pool rebuild replaces ``state`` wholesale (open_folder/append path).
    ctrl.state = GalleryState(items=items, mode=Mode.CAMERA)
    assert ctrl.state.metric_profile is None  # fresh state really lost it

    restored = ctrl.restore_metric_profile()

    assert restored == picked
    assert ctrl.state.metric_domain == "document"
    assert ctrl.state.metric_profile.domain == "document"


def test_auto_clears_the_pick_and_restores_the_mode_profile():
    items = [_item("a.png"), _item("b.png")]  # no measured metrics → no salience
    ctrl = _FakeController(items, mode=Mode.CAMERA)
    ctrl.set_metric_domain("synthetic")
    assert ctrl.state.metric_profile.domain == "synthetic"

    cleared = ctrl.set_metric_domain("auto")

    assert ctrl.state.metric_domain == ""
    assert cleared.domain == ""
    assert cleared == profile_for_mode(Mode.CAMERA)
    # A rebuild with no pick stays auto (nothing is re-applied).
    ctrl.state = GalleryState(items=items, mode=Mode.CAMERA)
    assert ctrl.restore_metric_profile() is None
    assert ctrl.refresh_metric_profile() == profile_for_mode(Mode.CAMERA)


def test_folder_switch_clears_the_pick():
    ctrl = _FakeController([_item("a.png")], mode=Mode.CAMERA)
    ctrl.set_metric_domain("photo")
    ctrl.clear_metric_profile()
    assert ctrl.state.metric_domain == ""
    assert ctrl.state.metric_profile is None
    ctrl.state = GalleryState(items=[], mode=Mode.CAMERA)
    assert ctrl.restore_metric_profile() is None


# --------------------------------------------------------------------------
# the analysis seam: ActionContext carries the pinned profile
# --------------------------------------------------------------------------


def test_action_context_carries_the_override_profile():
    ctrl = _FakeController([_item("a.png"), _item("b.png")], mode=Mode.CAMERA)
    picked = ctrl.set_metric_domain("document")
    owner = SimpleNamespace(
        state=ctrl.state,
        _judgment_domain="algorithms",
        _ai_settings_store=SimpleNamespace(
            load=lambda: SimpleNamespace(reasoning_effort="low")
        ),
    )

    ctx = build_context(owner, origin="action")

    assert ctx.profile == picked
    assert ctx.profile.domain == "document"
    assert ctx.mode == Mode.CAMERA


def test_vlm_outcome_cannot_replace_an_explicit_pick():
    ctrl = _FakeController([_item("a.png"), _item("b.png")], mode=Mode.CAMERA)
    picked = ctrl.set_metric_domain("document")

    vlm = MetricProfile(axis_ids=("brisque", "aesthetic"), source="vlm")
    ctrl._apply_profile_outcome(vlm, 0)

    assert ctrl.state.metric_profile == picked
    assert ctrl.state.metric_profile.domain == "document"
