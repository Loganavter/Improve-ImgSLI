"""Dot COLOUR codes the SCORE (band), never the instrument (owner 2026-10-27).

Owner report: "цветовое обозначение на точках везде голубое — по ним нельзя с
одного взгляда ориентироваться, а только при наведении с тултипом". Every
MEASURED judge dot painted ``_accent_color()`` (one blue token), so a card with a
90 / 60 / 20 scorecard read as three identical dots and the eye had to hover to
learn anything. The owner's rule: **colour = the score**, for a registry axis and
a judge-named axis alike — one number, one colour, whichever instrument produced
it. The provenance stays in the TEXT (``judged_axis_label`` still says
``name · measured by the judge``), so the two facts are no longer conflated.

This SUPERSEDES the colour half of P7-C item 6 (the accent-as-instrument marker);
the "one dot set, two phases, gaps suppressed" half is untouched.

Falsification story (red before this wave, on ``43f74634a``):

- ``test_three_judge_axes_score_bands_paint_three_colours`` — three judge axes at
  90 / 60 / 20 returned the SAME colour (the accent) three times, so the
  ``len(set(...)) == 3`` assertion failed on the old tree.
- ``test_one_number_is_one_colour_across_instruments`` — the same 80 % measured
  locally and by the judge resolved to two different colours (severity ``clean``
  vs the accent), so the equality assertion failed on the old tree.
- ``test_a_judge_dot_keeps_its_provenance_in_the_text`` passes before and after
  by design: it pins that removing the accent did NOT cost the hover fact.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.image_gallery.models import AiAnalysisResult, AiAxisProposal, GalleryItem, Mode
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.metric_scores import score_band
from tabs.image_gallery.ui.card.dots import (
    _BAND_SEVERITY,
    _accent_color,
    _severity_color,
    metric_dots_for_item,
)

#: Judge-NAMED axes — no registry id, no local detector, the normal AI answer.
_EDGE = AiAxisProposal(
    name="edge_definition",
    definition="crispness of high-contrast edges; 0 = mushy, 100 = razor",
    scale="0-100",
    direction="higher-is-better",
)
_GRAIN = AiAxisProposal(
    name="grain_uniformity",
    definition="evenness of the remaining grain; 0 = blotchy, 100 = even",
    scale="0-100",
    direction="higher-is-better",
)
_BANDING = AiAxisProposal(
    name="gradient_banding",
    definition="visible steps in smooth gradients; 0 = heavy, 100 = none",
    scale="0-100",
    direction="higher-is-better",
)


def _item(name: str, *, axes: dict | None = None, **metrics) -> GalleryItem:
    item = GalleryItem(path=Path(f"/gallery/{name}"), mtime_ns=1)
    item.metrics = dict(metrics)
    if axes is not None:
        item.analysis = AiAnalysisResult(
            description="",
            tags=(),
            model="m",
            analyzed_at_iso="t",
            axes=dict(axes),
        )
    return item


def _judge_profile(*entries) -> MetricProfile:
    """Judge-only axis set: a registry id the card asks for, three judge names.

    ``axis_ids`` is never empty (an axis-less profile is the ``NoProfileYet``
    refusal, not a render), and ``sharpness`` is unmeasured in the AI domain
    here, so the two-phase rule suppresses it and leaves the judge dots.
    """
    return MetricProfile(
        axis_ids=("sharpness",),
        mode="camera",
        source="vlm",
        axis_entries=tuple(entries),
    )


def _band_color(score: int) -> str:
    """The severity colour ``score_band`` asks for (the expected dot colour)."""
    return _severity_color(_BAND_SEVERITY[score_band(score)]).name().lower()


def test_three_judge_axes_score_bands_paint_three_colours() -> None:
    """90 / 60 / 20 = good / mid / bad = three DIFFERENT dot colours."""
    item = _item(
        "bands.png",
        axes={_EDGE.name: 90, _GRAIN.name: 60, _BANDING.name: 20},
    )
    profile = _judge_profile(_EDGE, _GRAIN, _BANDING)

    colors, infos = metric_dots_for_item(
        item, mode=Mode.CAMERA, domain="ai", profile=profile
    )

    assert [label.split(" · ")[0] for label, _score in infos] == [
        _EDGE.name,
        _GRAIN.name,
        _BANDING.name,
    ], infos
    assert [score for _label, score in infos] == [90, 60, 20], infos

    got = [color.name().lower() for color in colors]
    assert got == [_band_color(90), _band_color(60), _band_color(20)], (
        "a judge dot no longer paints the colour of its score band: "
        f"{got} vs {[_band_color(90), _band_color(60), _band_color(20)]}"
    )
    assert len(set(got)) == 3, (
        "three different scores still paint one colour — the dot cannot be read "
        f"without hovering (owner 2026-10-27): {got}"
    )
    accent = _accent_color().name().lower()
    assert accent not in got, (
        f"a judge dot still paints the instrument accent ({accent}), not its "
        f"band: {got}"
    )


def test_one_number_is_one_colour_across_instruments() -> None:
    """80 % measured locally == 80 % measured by the judge (same colour)."""
    local_item = _item("local.png", sharpness=320.0)  # 320 / 400 -> 80 %
    local_colors, local_infos = metric_dots_for_item(
        local_item, mode=Mode.CAMERA, domain="algorithms"
    )
    assert [score for _label, score in local_infos] == [80], local_infos

    judge_item = _item("judge.png", axes={_EDGE.name: 80})
    judge_colors, judge_infos = metric_dots_for_item(
        judge_item, mode=Mode.CAMERA, domain="ai", profile=_judge_profile(_EDGE)
    )
    assert [score for _label, score in judge_infos] == [80], judge_infos

    local = local_colors[0].name().lower()
    judge = judge_colors[0].name().lower()
    assert local == judge, (
        "the same number paints two colours depending on WHO measured it — the "
        f"dot colour must code the score, not the instrument: {local} vs {judge}"
    )
    assert local == _band_color(80), (
        f"the shared 80 % colour is not its band colour: {local} vs {_band_color(80)}"
    )


def test_a_judge_dot_keeps_its_provenance_in_the_text() -> None:
    """Colour is the band now; the hover TEXT still names the instrument."""
    item = _item("tooltip.png", axes={_EDGE.name: 90, _GRAIN.name: 20})
    profile = _judge_profile(_EDGE, _GRAIN)

    colors, infos = metric_dots_for_item(
        item, mode=Mode.CAMERA, domain="ai", profile=profile
    )

    assert len(infos) == 2, infos
    for label, _score in infos:
        assert "measured by the judge" in label, (
            f"the judge's provenance left the tooltip when the colour changed: {label}"
        )
    assert colors[0].name().lower() != colors[1].name().lower(), (
        "a 90 and a 20 painted the same colour: "
        f"{[c.name() for c in colors]}"
    )
