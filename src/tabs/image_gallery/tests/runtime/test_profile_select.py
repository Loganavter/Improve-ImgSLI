"""P1 — salience-derived profiles, the read accessor and the identity gate.

Falsification story (what each test would catch):

- spread computed from RAW values instead of 0–100 scores (a raw Laplacian
  variance and a 0–1 SSIM would be compared on one scale);
- an axis with a single measured value inventing a spread (or a "signal"
  from a lone item);
- the mode base being *replaced* rather than extended (a folder would lose
  the axes that already worked);
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

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.models import Mode
from tabs.image_gallery.services.metric_profile import MEASURED_POOL, MetricProfile
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.use_cases import profile_select
from tabs.image_gallery.use_cases.profile_select import (
    DEFAULT_SPREAD_FLOOR,
    active_profile,
    derive_for_state,
    derive_profile,
    describe,
    salience_axes,
)


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics=dict(metrics))


def _state(items, mode=None):
    return SimpleNamespace(items=list(items), mode=mode, source_path=None)


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
# the profile extends the mode base — it never replaces it
# --------------------------------------------------------------------------


def test_derive_profile_keeps_the_mode_base_and_adds_salient_axes():
    items = [
        _item("a.png", sharpness=0.0, ssim=0.9),
        _item("b.png", sharpness=400.0, ssim=0.9),
    ]
    profile = derive_profile(items, mode="fidelity")
    base = measured_axes_for("fidelity")
    assert set(base) <= set(profile.axis_ids)
    assert "sharpness" in profile.salient_axes
    # ssim is constant across the series → high score, zero spread → not salient.
    assert "ssim" not in profile.salient_axes
    assert profile.source == "heuristic"
    assert profile.mode == "fidelity"
    assert profile.axis_ids == tuple(a for a in MEASURED_POOL if a in set(profile.axis_ids))


def test_derive_profile_below_the_floor_is_exactly_the_mode_base():
    items = [
        _item("a.png", sharpness=0.0, ssim=0.9),
        _item("b.png", sharpness=400.0, ssim=0.9),
    ]
    profile = derive_profile(items, mode="camera", spread_floor=1000.0)
    assert profile.axis_ids == measured_axes_for("camera")
    assert profile.salient_axes == ()
    assert profile == derive_profile(items, mode="camera", spread_floor=1000.0)


def test_no_metrics_or_no_items_is_the_mode_base():
    assert derive_profile([], mode="camera").axis_ids == measured_axes_for("camera")
    assert derive_profile(None, mode="camera").axis_ids == measured_axes_for("camera")
    assert derive_profile([_item("a.png")], mode=None).axis_ids == measured_axes_for(None)


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


def test_a_bad_floor_falls_back_to_the_default():
    items = [
        _item("a.png", sharpness=0.0),
        _item("b.png", sharpness=400.0),
    ]
    assert derive_profile(items, mode="camera", spread_floor="nope") == derive_profile(
        items, mode="camera", spread_floor=DEFAULT_SPREAD_FLOOR
    )


def test_default_floor_sits_below_a_score_band_width():
    # Bands are 30 points wide (score_band 70/40) — one decisive step is 20.
    assert DEFAULT_SPREAD_FLOOR == 20.0


# --------------------------------------------------------------------------
# producer read (state) + consumer accessor
# --------------------------------------------------------------------------


def test_derive_for_state_reads_items_and_mode():
    state = _state(
        [_item("a.png", sharpness=0.0), _item("b.png", sharpness=400.0)],
        mode=Mode.CAMERA,
    )
    profile = derive_for_state(state)
    assert profile.mode == "camera"
    assert "sharpness" in profile.salient_axes


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


def test_profile_select_is_pure_no_qt_contract():
    source = Path(profile_select.__file__).read_text(encoding="utf-8")
    assert "PySide6" not in source and "import Qt" not in source


def test_module_exports_are_the_frozen_interface():
    assert set(profile_select.__all__) == {
        "DEFAULT_SPREAD_FLOOR",
        "active_profile",
        "derive_for_state",
        "derive_profile",
        "describe",
        "salience_axes",
    }
