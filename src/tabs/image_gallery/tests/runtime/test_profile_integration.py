"""Wave-2 identity gate — ONE metric profile reaches EVERY surface (plan P1).

The produce lane stores the profile and the consume lane reads it; each lane is
green alone. This file tests the **seam between them**, which is exactly where
multi-lane work fails: for one state, the stored profile must be the axis set
that the dots, the AI scorecard prompt, the rank fusion and the Jev measured
vector all resolve — byte for byte, not "a similar count".

Falsification stories (what each test would catch):

- the producer storing a profile nobody reads (every consumer silently keeping
  the mode mapping): a salient axis the mode base does not imply (`ssim` here —
  a ``reference`` axis absent from ``batch_synthetic``) must appear in EVERY
  surface;
- a consumer deriving its own axes (a second source of truth): the four
  surfaces must agree on the exact ordered id list, not merely on the count;
- the rank reading a different axis set from the dots/prompt: the fusion order
  must invert exactly when the stored profile restricts the axes, relative to
  the mode-mapping order;
- a fallback that diverges after invalidation: after ``clear_metric_profile``
  all four surfaces must fall back to the mode mapping together;
- non-determinism: two refreshes over unchanged inputs must produce equal
  profiles.

No Qt event loop, no GPU, no torch/PIL, no network: real controller primitives
over plain ``GalleryItem`` objects (the double style of
``runtime/test_profile_produce.py`` / ``tests/test_rank_wiring.py``).
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.controller import GalleryController
from tabs.image_gallery.models import GalleryItem, GalleryState, Mode, Series
from tabs.image_gallery.services.ai_client.prompt import _scorecard_axes, build_prompt
from tabs.image_gallery.services.jev_client import build_measured_vector
from tabs.image_gallery.services.metric_profile import profile_for_mode
from tabs.image_gallery.services.metric_scores import spec_for
from tabs.image_gallery.services.rank_fusion import measured_axes_for, rank_series
from tabs.image_gallery.ui.card.dots import metric_dots_for_item
from tabs.image_gallery.use_cases.profile_select import active_profile, describe

#: The axis the salience pass must add: a ``reference`` axis, i.e. one the
#: ``batch_synthetic`` mode base does NOT contain. If a surface shows it, that
#: surface read the stored profile rather than the mode mapping.
SALIENT = "ssim"


class _FakeController:
    """Minimal controller surface: the real unbound primitives over one state."""

    def __init__(self, items, series, mode=Mode.BATCH_SYNTHETIC) -> None:
        self.state = GalleryState(items=list(items), series=list(series), mode=mode)

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


def _scattered():
    """One series with a decisive spread on the reference axis ``ssim``.

    ``a`` matches the source but is noisy; ``b`` is clean but unlike the source.
    The mode mapping sees only ``noise`` (→ ``b`` wins); the salience-derived
    profile adds ``ssim`` (→ ``a`` wins). So the fusion order *is* the proof of
    which axis set the rank used.
    """
    a = _item("a.png", ssim=1.0, noise=0.9)
    b = _item("b.png", ssim=0.0, noise=0.0)
    return a, b


def _profile(ctrl):
    """The producer's profile, then the ONE accessor every consumer uses."""
    ctrl.refresh_metric_profile()
    return active_profile(ctrl.state)


# --------------------------------------------------------------------------
# the salient axis reaches every surface
# --------------------------------------------------------------------------


def test_the_stored_profile_is_salience_aware_and_deterministic() -> None:
    a, b = _scattered()
    ctrl = _FakeController([a, b], _series(a, b))
    assert ctrl.state.metric_profile is None  # pre-P1 default

    profile = _profile(ctrl)

    assert ctrl.state.metric_profile == profile
    assert SALIENT in profile.salient_axes, "the spread on ssim must be salient"
    assert set(profile.axis_ids) >= set(profile_for_mode(Mode.BATCH_SYNTHETIC).axis_ids)
    assert SALIENT not in measured_axes_for(Mode.BATCH_SYNTHETIC), (
        "the salient axis must NOT be part of the mode base, else this test "
        "cannot tell the profile apart from the mode mapping"
    )
    # Unchanged inputs → equal profile (determinism, plan §Acceptance).
    assert ctrl.refresh_metric_profile() == profile
    assert active_profile(ctrl.state) == profile


def test_card_dots_use_the_stored_profile() -> None:
    a, b = _scattered()
    ctrl = _FakeController([a, b], _series(a, b))
    profile = _profile(ctrl)

    colors, infos = metric_dots_for_item(a, mode=ctrl.state.mode, profile=profile)

    assert len(colors) == len(infos) == len(profile.axis_ids)
    labels = [label for label, _score in infos]
    expected = [
        (spec_for(axis).label if spec_for(axis) else axis) for axis in profile.axis_ids
    ]
    assert labels == expected
    assert (spec_for(SALIENT).label) in labels, "the salient axis is dotted"
    # Same axis count the mode mapping would give? No — that is the point.
    assert len(labels) > len(measured_axes_for(ctrl.state.mode))


def test_ai_scorecard_prompt_uses_the_stored_profile() -> None:
    a, b = _scattered()
    ctrl = _FakeController([a, b], _series(a, b))
    profile = _profile(ctrl)

    axes = _scorecard_axes(ctrl.state.mode, profile=profile)

    assert [axis for axis, _label in axes] == list(profile.axis_ids)
    text = build_prompt(ctrl.state.mode, profile=profile)
    label = spec_for(SALIENT).label
    assert f'"{SALIENT}": <0-100 {label}>' in text
    assert f'"{SALIENT}"' not in build_prompt(ctrl.state.mode)


def test_rank_fusion_uses_the_same_axis_set_as_the_other_surfaces() -> None:
    a, b = _scattered()
    ctrl = _FakeController([a, b], _series(a, b))
    profile = _profile(ctrl)
    members = list(ctrl.state.series[0].members)

    # What the four surfaces agree on.
    assert measured_axes_for(ctrl.state.mode, profile=profile) == profile.axis_ids
    expected = rank_series(members, mode=ctrl.state.mode, profile=profile)
    mode_only = rank_series(members, mode=ctrl.state.mode)
    assert expected != mode_only, (
        "the dataset must be discriminating, else rank identity proves nothing"
    )

    ctrl._apply_fusion_ranks(ctrl.state.series, mode=ctrl.state.mode)

    got = {str(item.path): item.rank for item in members}
    # The primitive ranks within the series; compare the ORDER, not the ids.
    assert _order(got) == _order(expected)


def test_jev_measured_vector_uses_the_stored_profile() -> None:
    a, b = _scattered()
    ctrl = _FakeController([a, b], _series(a, b))
    profile = _profile(ctrl)

    vector = build_measured_vector([a, b], mode=ctrl.state.mode, profile=profile)

    assert vector["mode"] == profile.mode
    assert len(vector["items"]) == 2
    for entry in vector["items"]:
        assert set(entry["scores"]) <= set(profile.axis_ids)
    by_alias = {entry["alias"]: entry["scores"] for entry in vector["items"]}
    assert by_alias["img_1"][SALIENT] == 100
    assert by_alias["img_2"][SALIENT] == 0
    assert by_alias["img_1"][SALIENT] > by_alias["img_2"][SALIENT]
    # Without the profile the vector carries the mode axes only — the salient
    # reference axis is absent for both items, which is what the profile added.
    plain = build_measured_vector([a, b], mode=ctrl.state.mode)
    assert all(SALIENT not in entry["scores"] for entry in plain["items"])


def test_trace_names_the_profile_and_its_source() -> None:
    a, b = _scattered()
    ctrl = _FakeController([a, b], _series(a, b))
    _profile(ctrl)

    text = describe(ctrl.state)

    assert "source=heuristic" in text
    assert "mode=batch_synthetic" in text
    salient_part = text.split("salient=", 1)[1]
    assert SALIENT in salient_part


# --------------------------------------------------------------------------
# invalidation: every surface falls back to the mode mapping together
# --------------------------------------------------------------------------


def test_clear_falls_back_identically_in_every_surface() -> None:
    a, b = _scattered()
    ctrl = _FakeController([a, b], _series(a, b))
    profile = _profile(ctrl)
    assert len(profile.axis_ids) > len(measured_axes_for(ctrl.state.mode))

    ctrl.clear_metric_profile()
    fallback = active_profile(ctrl.state)

    assert fallback == profile_for_mode(ctrl.state.mode)
    assert fallback.axis_ids == measured_axes_for(ctrl.state.mode)
    _colors, infos = metric_dots_for_item(a, mode=ctrl.state.mode, profile=fallback)
    assert len(infos) == len(fallback.axis_ids)
    assert [axis for axis, _label in _scorecard_axes(ctrl.state.mode, profile=fallback)] == list(
        fallback.axis_ids
    )
    vector = build_measured_vector([a, b], mode=ctrl.state.mode, profile=fallback)
    for entry in vector["items"]:
        assert set(entry["scores"]) <= set(fallback.axis_ids)


def test_a_consumer_without_state_is_unchanged() -> None:
    """The pre-P1 path must stay available: mode-only callers keep working."""
    a, b = _scattered()
    ctrl = _FakeController([a, b], _series(a, b))

    assert active_profile(None, mode=ctrl.state.mode) == profile_for_mode(
        ctrl.state.mode
    )
    _colors, infos = metric_dots_for_item(a, mode=ctrl.state.mode)
    assert len(infos) == len(measured_axes_for(ctrl.state.mode))
    assert [axis for axis, _label in _scorecard_axes(ctrl.state.mode)] == list(
        measured_axes_for(ctrl.state.mode)
    )


def _order(ranks: dict) -> list:
    """Paths sorted by their rank value (stable, comparable across primitives)."""
    return [path for path, _rank in sorted(ranks.items(), key=lambda kv: (kv[1], kv[0]))]
