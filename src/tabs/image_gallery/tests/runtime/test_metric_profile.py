"""P0 — the metric profile value object and the mode→axes seam.

Falsification story (what each test would catch):

- ``pool_axis_ids`` re-listing ids by hand instead of reading the registry
  (adding a detector to ``metric_scores.SPECS`` must extend the pool);
- the tag rule being re-implemented a second time (the profile and
  ``rank_fusion.measured_axes_for`` disagreeing about a mode's axes);
- an out-of-pool / duplicated / non-MEASURED id being accepted into a
  profile (a fabricated or drifted vocabulary);
- axis order depending on caller order or dict iteration (dots and report
  rows would shuffle between equal profiles);
- a profile that raises on garbage input (fail-open broken).

Pure-python ``SimpleNamespace`` fakes only — no Qt, no torch, no PIL.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tabs.image_gallery.backends.errors import NoProfileYet
from tabs.image_gallery.models import MetricKind, Mode
from tabs.image_gallery.services import metric_profile, rank_fusion
from tabs.image_gallery.services.metric_profile import (
    EXCLUDED_AXES,
    MEASURED_POOL,
    PROFILE_SOURCES,
    MetricProfile,
    format_profile,
    mode_id,
    pool_axis_ids,
    profile_for_mode,
)
from tabs.image_gallery.services.metric_scores import SPECS, spec_for
from tabs.image_gallery.services.rank_fusion import (
    item_quality,
    measured_axes_for,
    rank_series,
)

ALL_MODES = (None, "", "fidelity", "camera", "batch_synthetic", "nonsense", Mode.CAMERA)


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics=dict(metrics))


# --------------------------------------------------------------------------
# the pool is the registry, not a second list
# --------------------------------------------------------------------------


def test_pool_is_registry_derived_measured_and_ordered():
    expected = tuple(
        s.id
        for s in SPECS
        if s.kind is MetricKind.MEASURED and s.id not in EXCLUDED_AXES
    )
    assert MEASURED_POOL == expected
    assert pool_axis_ids() == MEASURED_POOL
    # Registry (report) order is the canonical order.
    positions = [s.id for s in SPECS if s.id in MEASURED_POOL]
    assert list(MEASURED_POOL) == positions
    assert len(set(MEASURED_POOL)) == len(MEASURED_POOL)


def test_pool_excludes_grouping_artefacts_and_non_measured_axes():
    for excluded in EXCLUDED_AXES:
        assert excluded not in MEASURED_POOL
    for axis_id in MEASURED_POOL:
        spec = spec_for(axis_id)
        assert spec is not None and spec.kind is MetricKind.MEASURED
    # An AI-only axis is not a local pool axis.
    assert "composition" not in MEASURED_POOL


# --------------------------------------------------------------------------
# one implementation of the mode rule (no second axis list)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ALL_MODES)
def test_profile_for_mode_is_the_rank_fusion_seam(mode):
    profile = profile_for_mode(mode)
    assert measured_axes_for(mode) == profile.axis_ids
    assert measured_axes_for(mode, profile=profile) == profile.axis_ids


def test_mode_scope_comes_from_registry_tags():
    fidelity = set(profile_for_mode("fidelity").axis_ids)
    camera = set(profile_for_mode("camera").axis_ids)
    batch = set(profile_for_mode("batch_synthetic").axis_ids)

    # Source-relative axes need a hub → fidelity only.
    assert {"ssim", "lpips", "dists", "color_accuracy"} <= fidelity
    assert not ({"ssim", "lpips"} & camera)
    assert not ({"ssim", "lpips"} & batch)
    # BRISQUE is the photographic (camera) no-reference axis.
    assert "brisque" in camera
    assert "brisque" not in fidelity
    assert "brisque" not in batch
    # Absolute local detectors apply everywhere.
    assert {"sharpness", "noise", "exposure"} <= (fidelity & camera & batch)
    # Unknown/empty mode = the mode-independent (untagged) set.
    assert set(profile_for_mode(None).axis_ids) == set(profile_for_mode("").axis_ids)


def test_existing_rank_fusion_public_names_still_resolve():
    # Backward-compatible re-exports (older callers/tests import these).
    assert rank_fusion.RANK_EXCLUDED_AXES == metric_profile.EXCLUDED_AXES
    # v3 = P2 salience (plan-gallery-ai-judgement): the fusion now drops the axes
    # whose series spread is inside the judge's noise floor, a semantics change
    # the version constant exists to announce.
    assert rank_fusion.RANK_FUSION_VERSION == 3
    # The profile is an optional kwarg — existing mode-only callers are intact.
    assert rank_fusion.measured_axes_for.__kwdefaults__ == {"profile": None}


# --------------------------------------------------------------------------
# the OFFER comes from the series (plan-gallery-ai-judgement P5)
# --------------------------------------------------------------------------


def test_profile_for_series_offers_the_measured_axes_above_the_floor():
    # Two axes move decisively; white_balance is constant (the live cel-art
    # shape: one picture, different processing).
    spreads = {"sharpness": 40.0, "noise": 30.0, "white_balance": 0.0}
    profile = metric_profile.profile_for_series(spreads, mode="camera")
    assert profile.source == "series"
    assert profile.axis_ids == ("sharpness", "noise"), "registry order, no extras"
    assert profile.salient_axes == profile.axis_ids
    assert "white_balance" not in profile.axis_ids, (
        "an axis whose spread is inside the floor was offered — the pre-P5 "
        "defect (asking the model about constants)"
    )


def test_profile_for_series_reads_the_one_floor_resolver_per_domain():
    # 10 score points: ABOVE the deterministic detectors' quantization floor,
    # INSIDE the stochastic judge's own noise. Same spreads, other domain, so
    # only the resolver (quality_read.axis_noise_floor) can explain the split.
    spreads = {"sharpness": 10.0}
    local = metric_profile.profile_for_series(spreads, mode="camera")
    assert local.source == "series" and local.axis_ids == ("sharpness",)
    judge = metric_profile.profile_for_series(spreads, mode="camera", domain="ai")
    assert judge.axis_ids == measured_axes_for("camera")
    assert judge == profile_for_mode("camera"), (
        "inside the judge's noise the offer must be the mode mapping fallback "
        f"(source={judge.source})"
    )


def test_profile_for_series_asks_the_resolver_instead_of_picking_a_number(monkeypatch):
    from tabs.image_gallery.services import quality_read

    monkeypatch.setattr(quality_read, "axis_noise_floor", lambda domain=None: 100.0)
    profile = metric_profile.profile_for_series({"sharpness": 40.0}, mode="camera")
    assert profile.source == "heuristic", (
        "a second floor number was used — the resolver was not consulted"
    )


def test_profile_for_series_is_one_offer_per_series_not_per_image():
    # The offer consumes the AGGREGATE spread, so its shape cannot depend on
    # how many members produced it: one axis set for the whole series (M1).
    spreads = {"sharpness": 40.0, "ssim": 35.0}
    assert metric_profile.profile_for_series(
        spreads, mode="fidelity", has_reference=True
    ) == metric_profile.profile_for_series(
        dict(spreads), mode="fidelity", has_reference=True
    )
    assert metric_profile.profile_for_series(
        spreads, mode="fidelity", has_reference=True
    ).axis_ids == ("sharpness", "ssim")


def test_profile_for_series_gates_reference_and_photo_axes():
    spreads = {"sharpness": 40.0, "ssim": 40.0, "brisque": 40.0}
    # No source hub → a source-relative axis measures nothing.
    no_source = metric_profile.profile_for_series(spreads, mode="fidelity")
    assert "ssim" not in no_source.axis_ids
    with_source = metric_profile.profile_for_series(
        spreads, mode="fidelity", has_reference=True
    )
    assert "ssim" in with_source.axis_ids
    # A photographic axis belongs to the camera mode only.
    assert "brisque" not in with_source.axis_ids
    assert "brisque" in metric_profile.profile_for_series(spreads, mode="camera").axis_ids


def test_profile_for_series_never_fabricates_or_raises_on_garbage():
    # Nothing measured that could separate the series → the mode mapping, which
    # is the LAST fallback (never a fabricated axis, never an exception).
    for garbage in (
        None,
        {},
        "nope",
        42,
        {"composition": 90.0, "typicality": 90.0, "not_an_axis": 90.0},
        {"sharpness": "nope"},
    ):
        profile = metric_profile.profile_for_series(garbage, mode="camera")
        assert profile.axis_ids == measured_axes_for("camera"), garbage
        assert profile.source == "heuristic", garbage


def test_profile_source_label_names_all_three_sources():
    label = metric_profile.profile_source_label
    assert label(MetricProfile(source="series")) == "series-derived"
    assert label(MetricProfile(source="vlm")) == "judge-vlm", (
        "the judge's own choice must stay distinguishable from the offer"
    )
    assert label(profile_for_mode("camera")) == "heuristic-camera (fallback)"
    assert "fallback" in label(None) and "fallback" in label(object())


# --------------------------------------------------------------------------
# the value object is closed, ordered and total
# --------------------------------------------------------------------------


def test_out_of_pool_duplicate_and_non_measured_ids_are_dropped():
    profile = MetricProfile(
        axis_ids=("brisque", "not_an_axis", "brisque", "composition", "typicality")
    )
    assert profile.axis_ids == ("brisque",)


def test_axis_order_is_registry_order_regardless_of_caller_order():
    forwards = MetricProfile(axis_ids=MEASURED_POOL)
    backwards = MetricProfile(axis_ids=tuple(reversed(MEASURED_POOL)))
    assert forwards.axis_ids == MEASURED_POOL
    assert backwards.axis_ids == MEASURED_POOL
    assert forwards == backwards


def test_mode_and_source_are_normalized():
    assert MetricProfile(mode=Mode.CAMERA).mode == "camera"
    assert MetricProfile(mode="  Fidelity ").mode == "fidelity"
    assert MetricProfile(mode=object()).mode == ""
    assert MetricProfile(source="VLM").source == "vlm"
    for bad in ("", "telepathy", None, 3):
        assert MetricProfile(source=bad).source == "heuristic"
    assert set(PROFILE_SOURCES) == {"series", "vlm", "heuristic"}


def test_salient_axes_are_a_subset_of_axis_ids_in_registry_order():
    profile = MetricProfile(
        axis_ids=("noise", "sharpness"), salient_axes=("sharpness", "brisque")
    )
    assert profile.axis_ids == ("sharpness", "noise")
    assert profile.salient_axes == ("sharpness",)


def test_profiles_are_hashable_and_equal_for_equal_inputs():
    a = MetricProfile(axis_ids=("noise", "sharpness"), mode="camera")
    b = MetricProfile(axis_ids=("sharpness", "noise"), mode=Mode.CAMERA)
    assert a == b and hash(a) == hash(b)
    assert len({a, b}) == 1
    assert bool(a) is True and len(a) == 2 and "noise" in a and "nope" not in a
    assert list(iter(a)) == ["sharpness", "noise"]


def test_empty_profile_is_falsy_and_never_raises():
    assert bool(MetricProfile()) is False
    for garbage in (None, 123, "sharpness", object()):
        profile = MetricProfile(axis_ids=garbage, salient_axes=garbage, mode=garbage)
        assert isinstance(profile.axis_ids, tuple)


def test_format_profile_names_axes_source_and_mode():
    text = format_profile(MetricProfile(axis_ids=("sharpness",), mode="camera"))
    assert "axes=sharpness" in text and "source=heuristic" in text and "mode=camera" in text
    assert "salient=" not in text
    with_salient = format_profile(
        MetricProfile(axis_ids=("sharpness", "noise"), salient_axes=("noise",))
    )
    assert "salient=noise" in with_salient
    assert "axes=-" in format_profile(MetricProfile())
    for garbage in (None, 7, object()):
        assert "axes=" in format_profile(garbage)


def test_mode_id_normalizes_like_the_registry_enum():
    assert mode_id(Mode.BATCH_SYNTHETIC) == "batch_synthetic"
    assert mode_id("CAMERA") == "camera"
    assert mode_id(" camera ") == "camera"
    assert mode_id(None) == "" and mode_id("nope") == "" and mode_id(object()) == ""


# --------------------------------------------------------------------------
# the profile is the axis selector for the whole fusion
# --------------------------------------------------------------------------


def test_explicit_profile_wins_and_an_empty_one_is_no_profile_yet():
    only_sharpness = MetricProfile(axis_ids=("sharpness",))
    assert measured_axes_for("camera", profile=only_sharpness) == ("sharpness",)
    # ADR 009 A3: a profile with no axis is a backend with nothing to measure,
    # so it is NoProfileYet — the LOCAL mode mapping is NOT a repair (that
    # fallback is what fed an empty AI profile the detector axis set).
    with pytest.raises(NoProfileYet):
        measured_axes_for("camera", profile=MetricProfile())
    # Duck-typed: any object with .axis_ids is accepted (no isinstance gate).
    assert measured_axes_for("camera", profile=SimpleNamespace(axis_ids=("noise",))) == ("noise",)


def test_fusion_uses_the_profile_axis_set():
    item = _item("a.png", sharpness=320.0, ssim=0.5)
    # sharpness 320/400 → 80 %; ssim 0.5 → 50 %; mean 65, worst-cap 50+20=70 → 65.
    assert item_quality(item, mode="fidelity") == 65
    assert item_quality(item, mode="fidelity", profile=MetricProfile(axis_ids=("sharpness",))) == 80
    ranks = rank_series(
        [_item("a.png", sharpness=320.0), _item("b.png", sharpness=100.0)],
        mode="camera",
        profile=MetricProfile(axis_ids=("sharpness",)),
    )
    assert ranks == {"/gallery/a.png": 1, "/gallery/b.png": 2}
