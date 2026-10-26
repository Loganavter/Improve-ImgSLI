"""P1 consume side — dots, AI scorecard and analysis read the ACTIVE profile.

Every consumer that used to decide its axes from ``measured_axes_for(mode)``
must instead take the active profile, so the dots, the AI scorecard prompt, the
analysis request and the rank agree on ONE axis set — and a folder with no
stored profile keeps the pre-P1 mode mapping (fail-open).

Falsification story (what each test would catch):

- a consumer still calling ``measured_axes_for(mode)`` without ``profile``
  (the prompt/dots would show the mode's axes, not the profile's);
- the profile honoured by the pure helper but dropped by the grid-card /
  list-row widget path;
- ``grid_view`` caching the profile on the widget (stale after a re-derive):
  the resolution must read the LIVE ``state.algorithms_profile`` and return
  ``None`` when absent;
- ``_begin_analysis`` forgetting to pass the active profile to the request;
- a ``profile=None`` changing the pre-P1 (mode mapping) output.

Pure-python fakes where possible; the card tests follow ``test_metric_dots.py``
(``QT_QPA_PLATFORM=offscreen`` is set in the suite).
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.services.ai_client.prompt import _scorecard_axes, build_prompt
from tabs.image_gallery.services.metric_profile import MetricProfile, profile_for_mode
from tabs.image_gallery.services.metric_scores import spec_for
from tabs.image_gallery.services.rank_fusion import measured_axes_for
from tabs.image_gallery.ui.card import build_gallery_card
from tabs.image_gallery.tests._activity_fixtures import mark_analyzing
from tabs.image_gallery.ui.card.dots import metric_dots_for_item
from tabs.image_gallery.ui.grid_view.rebuild import _resolve_profile
from tabs.image_gallery.ui.list.card import build_gallery_list_card

#: A restricted profile: one axis, a subset of what ``camera`` would offer.
P_RESTRICTED = MetricProfile(axis_ids=("sharpness",))
#: A widened profile: adds axes ``camera`` does NOT offer (fidelity-only).
P_WIDENED = MetricProfile(axis_ids=("sharpness", "ssim", "lpips"))
#: The AI backend's own answer: the same widened axes, judge-tagged. The AI slot
#: accepts only ``source="vlm"`` (backend-isolation invariant I1).
P_AI = MetricProfile(axis_ids=("sharpness", "ssim", "lpips"), source="vlm")


def _item(**overrides) -> GalleryItem:
    defaults = dict(path=Path("/gallery/a.png"), mtime_ns=1)
    defaults.update(overrides)
    return GalleryItem(**defaults)


def _labels(axes) -> list[str]:
    return [(spec_for(a).label if spec_for(a) else a) for a in axes]


# ---------------------------------------------------------------------------
# AI scorecard prompt
# ---------------------------------------------------------------------------


def test_prompt_requests_only_the_profile_axes() -> None:
    axes = _scorecard_axes("camera", profile=P_RESTRICTED)
    assert axes == (("sharpness", "Sharpness"),)
    text = build_prompt("camera", profile=P_RESTRICTED)
    assert '"sharpness": <0-100 Sharpness>' in text
    # The camera-only axis and the rest of the mode set are NOT requested.
    assert '"brisque"' not in text
    assert '"exposure"' not in text


def test_prompt_widened_profile_requests_axes_the_mode_would_not() -> None:
    # ``ssim`` / ``lpips`` are fidelity-only — camera never offers them.
    assert "ssim" not in measured_axes_for("camera")
    assert "lpips" not in measured_axes_for("camera")
    axes = _scorecard_axes("camera", profile=P_WIDENED)
    assert [a for a, _label in axes] == list(P_WIDENED.axis_ids)
    text = build_prompt("camera", profile=P_WIDENED)
    assert '"ssim"' in text and '"lpips"' in text


def test_prompt_without_profile_is_byte_identical_to_the_mode_set() -> None:
    for mode in ("camera", "fidelity", "batch_synthetic", None):
        assert _scorecard_axes(mode) == _scorecard_axes(mode, profile=None)
        assert [a for a, _l in _scorecard_axes(mode)] == list(measured_axes_for(mode))
        assert build_prompt(mode) == build_prompt(mode, profile=None)
        # Passing the mode mapping as a profile is the SAME prompt (the profile
        # beats the mode but resolves to the identical axis set).
        assert build_prompt(mode) == build_prompt(
            mode, profile=profile_for_mode(mode)
        )


def test_build_request_forwards_profile_into_the_prompt(tmp_path) -> None:
    from tabs.image_gallery.services.ai_client import build_request

    img = tmp_path / "i.png"
    img.write_bytes(b"\x00")
    text = build_request(img, model="m", mode="camera", profile=P_RESTRICTED)[
        "messages"
    ][0]["content"][0]["text"]
    assert '"sharpness"' in text
    assert '"brisque"' not in text and '"exposure"' not in text
    # profile=None is the untouched mode request.
    assert build_request(img, model="m", mode="camera") == build_request(
        img, model="m", mode="camera", profile=None
    )


# ---------------------------------------------------------------------------
# metric dots (pure helper)
# ---------------------------------------------------------------------------


def test_metric_dots_restricted_profile_has_one_dot() -> None:
    colors, infos = metric_dots_for_item(mark_analyzing(_item()), mode="camera", profile=P_RESTRICTED)
    assert len(colors) == len(P_RESTRICTED.axis_ids) == 1
    assert [label for label, _score in infos] == ["Sharpness"]


def test_metric_dots_widened_profile_keeps_profile_order_and_labels() -> None:
    colors, infos = metric_dots_for_item(mark_analyzing(_item()), mode="camera", profile=P_WIDENED)
    assert len(colors) == len(P_WIDENED.axis_ids) == 3
    assert [label for label, _score in infos] == _labels(P_WIDENED.axis_ids)
    # The mode alone would have offered a DIFFERENT count — proving the profile
    # (not the mode) decided the dot set.
    assert len(P_WIDENED.axis_ids) != len(measured_axes_for("camera"))


def test_metric_dots_backward_compatible_without_profile() -> None:
    item = mark_analyzing(_item())
    for mode in ("camera", "fidelity", "batch_synthetic", None):
        colors, infos = metric_dots_for_item(item, mode=mode)
        colors_none, infos_none = metric_dots_for_item(item, mode=mode, profile=None)
        assert len(colors) == len(measured_axes_for(mode))
        assert len(colors_none) == len(colors)
        assert infos_none == infos
        assert [label for label, _score in infos] == _labels(measured_axes_for(mode))


# ---------------------------------------------------------------------------
# widget paths (grid card + list row)
# ---------------------------------------------------------------------------


def test_grid_card_honours_the_profile(qapp) -> None:
    card = build_gallery_card(mark_analyzing(_item()), parent=None, mode="camera", profile=P_WIDENED)
    assert len(card._gallery_dot_colors) == len(P_WIDENED.axis_ids) == 3
    assert [label for label, _score in card._gallery_dot_infos] == _labels(
        P_WIDENED.axis_ids
    )
    card.deleteLater()

    restricted = build_gallery_card(
        mark_analyzing(_item()), parent=None, mode="camera", profile=P_RESTRICTED
    )
    assert len(restricted._gallery_dot_colors) == 1
    restricted.deleteLater()

    # Without a profile the card keeps the mode-mapping parity.
    plain = build_gallery_card(mark_analyzing(_item()), parent=None, mode="camera")
    assert len(plain._gallery_dot_colors) == len(measured_axes_for("camera"))
    plain.deleteLater()


def test_list_row_honours_the_profile(qapp) -> None:
    card = build_gallery_list_card(
        mark_analyzing(_item()), mode="camera", domain="algorithms", profile=P_WIDENED
    )
    assert len(card._gallery_dot_colors) == len(P_WIDENED.axis_ids)
    assert len(card._gallery_dot_infos) == len(P_WIDENED.axis_ids)
    card.deleteLater()


# ---------------------------------------------------------------------------
# grid_view resolution: LIVE state, never cached
# ---------------------------------------------------------------------------


def _fake_view(stored_profile, *, mode="camera"):
    state = SimpleNamespace(algorithms_profile=stored_profile, mode=mode)
    parent = SimpleNamespace(state=state, parent=lambda: None)
    return SimpleNamespace(parent=lambda: parent, window=lambda: None)


def test_grid_view_resolves_the_live_stored_profile() -> None:
    view = _fake_view(P_WIDENED)
    assert _resolve_profile(view) is P_WIDENED


def test_grid_view_resolves_to_none_without_a_stored_profile() -> None:
    assert _resolve_profile(_fake_view(None)) is None


def test_grid_view_explicit_profile_wins() -> None:
    view = _fake_view(None)
    assert _resolve_profile(view, P_RESTRICTED) is P_RESTRICTED


# ---------------------------------------------------------------------------
# analysis request carries the active profile (ai_analysis._begin_analysis)
# ---------------------------------------------------------------------------


def _bare_controller(items):
    from tabs.image_gallery.controller import GalleryController

    ctl = GalleryController.__new__(GalleryController)
    ctl.state = SimpleNamespace(items=items)
    ctl.widget = SimpleNamespace(refresh_card=lambda item: None)
    ctl._folder_gen = 0
    ctl._judgment_domain = "ai"
    ctl._tr = lambda key, default: default
    ctl._ai_settings_store = SimpleNamespace(
        load=lambda: SimpleNamespace(
            enabled=True, api_key="k", model="m", base_url="http://h"
        )
    )
    return ctl


def _capturing_worker(seen):
    class _FakeWorker:
        def __init__(self, fn, *args, **kwargs):
            seen["kwargs"] = kwargs
            self.signals = SimpleNamespace(
                result=SimpleNamespace(connect=lambda *a, **k: None),
                error=SimpleNamespace(connect=lambda *a, **k: None),
            )

    return _FakeWorker


def test_begin_analysis_passes_the_active_profile(monkeypatch) -> None:
    from tabs.image_gallery.use_cases import ai_analysis

    item = mark_analyzing(_item())
    ctl = _bare_controller([item])
    ctl.state = SimpleNamespace(
        items=[item], mode="camera", ai_profile=P_AI
    )
    seen: dict = {}
    monkeypatch.setattr(ai_analysis, "GenericWorker", _capturing_worker(seen))
    monkeypatch.setattr(ctl, "_pool_start", lambda *a, **k: None, raising=False)
    from tabs.image_gallery.use_cases.action_context import build_context

    ctx = build_context(ctl, origin="action", card_path=item.path)
    assert ctx.profile is P_AI
    ctl._begin_analysis(ctx, item)
    assert seen["kwargs"].get("profile") is P_AI


def test_begin_analysis_never_borrows_the_local_mode_profile(monkeypatch) -> None:
    """An empty AI slot is an EMPTY judge profile — not the local mode mapping.

    Owner rule 2026-10-26 (backend isolation): the AI backend never falls back to
    locally derived axes. Before the split there was one slot, so a state with no
    stored profile made the AI request carry ``profile_for_mode("camera")`` —
    exactly the cross-backend borrow.
    """
    from tabs.image_gallery.use_cases import ai_analysis

    item = mark_analyzing(_item())
    ctl = _bare_controller([item])
    ctl.state = SimpleNamespace(items=[item], mode="camera")  # no stored profile
    seen: dict = {}
    monkeypatch.setattr(ai_analysis, "GenericWorker", _capturing_worker(seen))
    monkeypatch.setattr(ctl, "_pool_start", lambda *a, **k: None, raising=False)
    from tabs.image_gallery.use_cases.action_context import build_context

    ctx = build_context(ctl, origin="action", card_path=item.path)
    ctl._begin_analysis(ctx, item)
    carried = seen["kwargs"]["profile"]
    assert carried == MetricProfile(mode="camera", source="vlm")
    assert carried.axis_ids == () and carried.axis_entries == ()
    assert carried != profile_for_mode("camera")
