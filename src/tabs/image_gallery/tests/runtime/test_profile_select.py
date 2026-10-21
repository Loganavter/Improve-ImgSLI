"""The series-derived profile offer, the read accessor and the identity gate.

Falsification story (what each test would catch):

- spread computed from RAW values instead of 0–100 scores (a raw Laplacian
  variance and a 0–1 SSIM would be compared on one scale);
- an axis with a single measured value inventing a spread (or a "signal"
  from a lone item);
- the mode mapping being MERGED into a measured offer — the pre-P5 defect that
  kept asking the model about white balance/aesthetic on a series where
  they are constant by construction (plan-gallery-ai-judgement J4/P5);
- an axis inside the local instrument's noise floor being offered anyway;
- the mode mapping not being the LAST fallback (and not NAMED as one) when the
  series has no discriminating measurement at all;
- a salience threshold that is order-dependent (dict/set iteration leaking
  into the profile) — checked by permutation equality;
- ``active_profile`` ignoring a stored profile, or throwing it away when the
  stored one is empty/unusable, or raising on a garbage state;
- a profile derived without any metrics silently becoming the whole pool.

Pure-python ``SimpleNamespace`` fakes only — no Qt, no torch, no PIL.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.models import Mode
from tabs.image_gallery.services.metric_profile import MEASURED_POOL, MetricProfile
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.use_cases import profile_select
from tabs.image_gallery.use_cases.profile_select import (
    active_profile,
    derive_for_state,
    derive_profile,
    describe,
    describe_source,
    salience_axes,
)


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics=dict(metrics))


def _state(items, mode=None, *, source_path=None):
    return SimpleNamespace(
        items=list(items), mode=mode, source_path=source_path
    )


# --------------------------------------------------------------------------
# salience is measured on the 0-100 score, and needs two values
# --------------------------------------------------------------------------


def test_spread_is_computed_on_scores_not_raw_values():
    # sharpness raw 0 vs 400 → scores 0 vs 100 (a raw-space spread would be 400).
    axes = dict(salience_axes([_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)]))
    assert axes["sharpness"] == 100.0


def test_a_single_measured_value_has_no_spread():
    axes = dict(salience_axes([_item("a.png", noise=0.5), _item("b.png")]))
    assert "noise" not in axes
    assert salience_axes([_item("a.png", noise=0.5)]) == ()


def test_unmeasured_and_excluded_axes_never_appear():
    axes = dict(
        salience_axes(
            [
                _item("a.png", ssim=0.9, **{"embedding_dist_to_centroid": 0.9}),
                _item("b.png", ssim=0.1, **{"embedding_dist_to_centroid": 0.1}),
            ]
        )
    )
    assert "typicality" not in axes
    assert set(axes) <= set(MEASURED_POOL)


def test_salience_axes_are_sorted_by_spread_then_registry_order():
    items = [
        _item("a.png", sharpness=0.0, noise=0.9),
        _item("b.png", sharpness=400.0, noise=1.0),
    ]
    axes = salience_axes(items)
    assert [value for _axis, value in axes] == sorted(
        [value for _axis, value in axes], reverse=True
    )
    # Equal spreads keep registry order (sharpness precedes noise in SPECS).
    assert [axis for axis, _value in axes] == ["sharpness", "noise"]


def test_salience_never_raises_on_garbage():
    assert salience_axes(None) == ()
    assert salience_axes([None, 3, "x"]) == ()
    assert salience_axes([SimpleNamespace(path=Path("a")), SimpleNamespace()]) == ()


# --------------------------------------------------------------------------
# the offer comes from the series — the mode base is never merged in
# --------------------------------------------------------------------------


def test_derive_profile_offers_only_axes_that_separate_the_series():
    # sharpness moves across the two variants; white_balance and aesthetic are
    # constant (the live cel-art shape: same picture, different processing).
    items = [
        _item("a.png", sharpness=0.0, wb_shift=0.9, aesthetic=0.8),
        _item("b.png", sharpness=400.0, wb_shift=0.9, aesthetic=0.8),
    ]
    profile = derive_profile(items, mode="camera")
    assert profile.axis_ids == ("sharpness",)
    assert "white_balance" not in profile.axis_ids
    assert "aesthetic" not in profile.axis_ids
    assert profile.source == "series"
    assert profile.salient_axes == ("sharpness",)
    assert profile.mode == "camera"
    # The mode mapping still describes the pool, but it is NOT the offer.
    assert "white_balance" in measured_axes_for("camera")


def test_an_axis_inside_the_local_floor_is_not_offered():
    # sharpness raw 200 vs 204 → scores 50 vs 51: a 1-point spread, i.e. integer
    # quantization of deterministic detectors — inside the floor (1.0).
    items = [_item("a.png", sharpness=200.0), _item("b.png", sharpness=204.0)]
    profile = derive_profile(items, mode="camera")
    assert profile.source == "heuristic", (
        "a series with no discriminating measurement must fall back to the mode "
        f"mapping (marked as a fallback), got {profile.source!r}"
    )
    assert profile.axis_ids == measured_axes_for("camera")


def test_no_measurements_at_all_is_the_mode_fallback():
    for items in ([], None, [_item("a.png")]):
        profile = derive_profile(items, mode="camera")
        assert profile.axis_ids == measured_axes_for("camera")
        assert profile.source == "heuristic"
    assert describe_source(_state([], mode="camera")) == "heuristic-camera (fallback)"


def test_reference_axes_need_a_source_but_still_need_a_spread():
    # ssim moves across the variants; sharpness does too.
    items = [
        _item("a.png", sharpness=0.0, ssim=0.10),
        _item("b.png", sharpness=400.0, ssim=0.90),
    ]
    without = derive_profile(items, mode="fidelity", has_reference=False)
    assert "ssim" not in without.axis_ids, (
        "a source-relative axis must not be offered without a source hub"
    )
    with_source = derive_profile(items, mode="fidelity", has_reference=True)
    assert "ssim" in with_source.axis_ids
    assert with_source.source == "series"
    # An optional reference backend that never ran measured nothing: it is not
    # offered on the mere existence of a source (no spread, no evidence).
    assert "lpips" not in with_source.axis_ids
    assert "dists" not in with_source.axis_ids


def test_derive_profile_is_deterministic_under_permutation_and_rebuild():
    items = [
        _item("a.png", sharpness=0.0, noise=0.9),
        _item("b.png", sharpness=400.0, noise=1.0),
        _item("c.png", sharpness=200.0),
    ]
    first = derive_profile(items, mode="camera")
    assert first == derive_profile(list(reversed(items)), mode="camera")
    rebuilt = [
        _item("c.png", sharpness=200.0),
        _item("a.png", sharpness=0.0, noise=0.9),
        _item("b.png", sharpness=400.0, noise=1.0),
    ]
    assert first == derive_profile(rebuilt, mode="camera")


# --------------------------------------------------------------------------
# producer read (state) + consumer accessor
# --------------------------------------------------------------------------


def test_derive_for_state_reads_items_mode_and_the_source_hub():
    state = _state(
        [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)],
        mode=Mode.CAMERA,
    )
    profile = derive_for_state(state)
    assert profile.mode == "camera"
    assert profile.axis_ids == ("sharpness",)
    assert profile.source == "series"

    fidelity = _state(
        [
            _item("a.png", sharpness=0.0, ssim=0.10),
            _item("b.png", sharpness=400.0, ssim=0.90),
        ],
        mode=Mode.FIDELITY,
        source_path=Path("/gallery/source.png"),
    )
    with_source = derive_for_state(fidelity)
    assert "ssim" in with_source.axis_ids, (
        "a fidelity series with a source hub must be offered its measured "
        "source-relative axes"
    )


def test_derive_for_state_never_raises():
    assert derive_for_state(None).mode == ""
    assert derive_for_state(SimpleNamespace()).axis_ids == measured_axes_for(None)
    assert derive_for_state(SimpleNamespace(items=object(), mode=object())).mode == ""


def test_active_profile_prefers_the_stored_profile():
    stored = MetricProfile(axis_ids=("sharpness",), mode="camera", salient_axes=("sharpness",))
    state = SimpleNamespace(items=[], mode=Mode.FIDELITY, metric_profile=stored)
    assert active_profile(state) is stored
    assert active_profile(state, mode=Mode.CAMERA) is stored


def test_active_profile_falls_back_to_the_mode_mapping():
    # No state at all (a consumer that only holds a mode) → pre-P1 behaviour.
    for mode in (None, "fidelity", "camera", Mode.BATCH_SYNTHETIC):
        assert active_profile(None, mode=mode) == derive_profile([], mode=mode)
        assert active_profile(None, mode=mode).axis_ids == measured_axes_for(mode)
    state = SimpleNamespace(items=[], mode=Mode.CAMERA)
    assert active_profile(state) == derive_profile([], mode="camera")
    # A garbage/empty cache is not a usable profile → the mode base applies.
    for bad in (None, "profile", MetricProfile(), object()):
        state = SimpleNamespace(mode=Mode.CAMERA, metric_profile=bad)
        assert active_profile(state).axis_ids == measured_axes_for("camera")
    assert active_profile(object()).axis_ids == measured_axes_for(None)


def test_describe_names_the_profile_source_and_mode():
    state = SimpleNamespace(items=[], mode=Mode.CAMERA)
    text = describe(state)
    assert "source=heuristic" in text and "mode=camera" in text and "axes=" in text
    assert describe_source(state) == "heuristic-camera (fallback)"


def test_profile_select_is_pure_no_qt_contract():
    source = Path(profile_select.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in source and "import Qt" not in source


def test_module_exports_are_the_frozen_interface():
    assert set(profile_select.__all__) == {
        "active_profile",
        "derive_for_state",
        "derive_profile",
        "describe",
        "describe_source",
        "salience_axes",
    }
