"""Free-axes AI profile → card dots on the LIVE build path (both views).

Owner report 2026-10-27: Quick Look rows carried the judge's six free axes while
the gallery cards showed NO dots at all — in the grid and in the list alike. The
dots helper was fine (``tests/test_metric_dots.py``,
``runtime/test_judge_p7c_visible_axes.py::test_card_dots_show_the_judge_axes...``
call it with an explicit ``profile=``), so the loss was between the live rebuild
and the card: the grid asked its parent/window chain for ``state`` and found
none (the widget keeps ``_session_state``; the grid is reparented into the
content stack), so every card got ``profile=None``. A ``None`` profile resolves
the LOCAL mode mapping, which in the AI domain has no producer for the judge's
names → every asked axis is a ``gap`` → nothing measured and nothing in flight →
``metric_dots_for_item`` correctly paints nothing.

Falsification story (red before the fix): every test here drives the REAL path
(``GalleryGridView.rebuild_grid`` / ``set_view_mode`` → ``_acquire_card`` →
``build_*_card``/``update_*_card``) with the AI profile stored where the live
controller stores it (``state.ai_profile``) and the domain where the controller
keeps it (``owner._judgment_domain``). On the pre-fix tree ``_resolve_profile``
returned ``None`` and the cards carried ``_gallery_dot_colors == ()`` — the
assertions below fail with "0 dots" while the very same profile yields six
colours through the helper, which is the differential this file pins.

The two-phase rule is asserted too, deliberately unchanged: an IDLE card with no
measurement paints NOTHING (a finished card must not show pending grey), so
"fixing" the dots by always painting the asked set would fail here.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import (
    AiAnalysisResult,
    AiAxisProposal,
    GalleryItem,
    Mode,
)
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.metric_scores import score_band
from tabs.image_gallery.ui.card.dots import (
    _BAND_SEVERITY,
    _severity_color,
    dot_tooltip_text,
)
from tabs.image_gallery.ui.grid_view import GalleryGridView

#: The six axes the judge named in the owner's live report (profile_ai.py:753):
#: none of them is a registry id, so the LOCAL mode mapping cannot name them.
FREE_AXES = (
    "line_crispness",
    "denoise_smoothness",
    "color_saturation",
    "gradient_banding",
    "detail_preservation",
    "halo_artifacts",
)
#: The judge's per-card numbers for those axes (row values the owner saw).
FREE_SCORES = {name: 55 + 5 * i for i, name in enumerate(FREE_AXES)}


def _band_colors(names, scores) -> list[str]:
    """Expected dot colours: each score's severity band (owner 2026-10-27).

    The dot colour codes the SCORE, for a judge number and a detector number
    alike; the instrument is a label/tooltip fact only.
    """
    return [
        _severity_color(_BAND_SEVERITY[score_band(scores[name])]).name()
        for name in names
    ]


def _entries() -> tuple[AiAxisProposal, ...]:
    return tuple(
        AiAxisProposal(
            name=name,
            definition=f"{name}; 0 = none visible, 100 = heavy",
            scale="0-100",
            direction="higher-is-better",
        )
        for name in FREE_AXES
    )


def _ai_profile() -> MetricProfile:
    """The profile shape the live log printed: ``axes=-``, six judged axes."""
    return MetricProfile(
        axis_ids=(),
        mode="camera",
        source="vlm",
        axis_entries=_entries(),
    )


def _item(*, axes: dict | None = None, metrics: dict | None = None) -> GalleryItem:
    item = GalleryItem(path=Path("/gallery/ai_dots.png"), mtime_ns=1)
    item.mode = Mode.CAMERA
    if axes is not None:
        item.analysis = AiAnalysisResult(
            description="",
            tags=(),
            model="m",
            analyzed_at_iso="t",
            axes=dict(axes),
        )
    if metrics is not None:
        item.metrics = dict(metrics)
    return item


def _live_grid(profile, *, domain: str = "ai", item: GalleryItem) -> GalleryGridView:
    """A grid bound the way the live widget binds it (owner + state slot).

    ``_gallery_widget`` is the widget-side back-ref the live page sets in
    ``ImageGalleryWidget.__init__``; ``_owner_for_triage`` is its documented
    resolver (attached controller, or the widget itself). The state carries the
    profile in the AI backend's OWN slot, exactly as
    ``backends.ai.profile.install`` writes it.
    """
    gv = GalleryGridView()
    owner = SimpleNamespace(
        _judgment_domain=domain,
        state=SimpleNamespace(
            mode=Mode.CAMERA,
            ai_profile=profile,
            algorithms_profile=None,
            judgment_domain=domain,
        ),
    )
    gv._gallery_widget = SimpleNamespace(_owner_for_triage=lambda: owner)
    gv.rebuild_grid([item], mode=Mode.CAMERA)
    return gv


def _card(gv: GalleryGridView, item: GalleryItem):
    card = gv.card_for(item.path)
    assert card is not None, "the live rebuild produced no card"
    return card


@pytest.fixture()
def qapp_ready(qapp):
    QApplication.processEvents()
    return qapp


def test_grid_card_dots_are_the_judge_axes_on_the_live_path(qapp_ready):
    """A grid card paints one BAND-coloured dot per MEASURED judge axis."""
    item = _item(axes=FREE_SCORES)
    gv = _live_grid(_ai_profile(), item=item)
    card = _card(gv, item)

    colors = tuple(getattr(card, "_gallery_dot_colors", ()) or ())
    infos = tuple(getattr(card, "_gallery_dot_infos", ()) or ())

    assert len(colors) == len(FREE_AXES), (
        "the live grid card carried no dots for the judge's axes "
        f"({len(colors)} painted) — the profile never reached the card"
    )
    assert getattr(card, "_gallery_domain", None) == "ai", (
        "the card read the wrong judgment domain"
    )
    expected = _band_colors(FREE_AXES, FREE_SCORES)
    assert [c.name() for c in colors] == expected, (
        "a judge number no longer paints the colour of its score band "
        f"({expected} expected): {[c.name() for c in colors]}"
    )
    assert [info[1] for info in infos] == [FREE_SCORES[n] for n in FREE_AXES], (
        f"the dots do not carry the judge's numbers: {infos}"
    )
    for name, info in zip(FREE_AXES, infos):
        tooltip = dot_tooltip_text(info)
        assert name in tooltip and tooltip.endswith(f"{FREE_SCORES[name]}%"), (
            f"dot tooltip for {name!r} is not '<label>: N%': {tooltip!r}"
        )
    gv.deleteLater()


def test_list_row_dots_are_the_judge_axes_on_the_live_path(qapp_ready):
    """The list row paints the same dots (parity, same resolver)."""
    item = _item(axes=FREE_SCORES)
    gv = _live_grid(_ai_profile(), item=item)
    gv.set_view_mode(True)  # list
    row = _card(gv, item)

    colors = tuple(getattr(row, "_gallery_dot_colors", ()) or ())
    infos = tuple(getattr(row, "_gallery_dot_infos", ()) or ())

    assert len(colors) == len(FREE_AXES), (
        f"the live list row carried {len(colors)} dots, expected {len(FREE_AXES)}"
    )
    assert [c.name() for c in colors] == _band_colors(FREE_AXES, FREE_SCORES)
    assert [info[1] for info in infos] == [FREE_SCORES[n] for n in FREE_AXES]
    gv.deleteLater()


def test_a_live_refresh_after_the_profile_lands_fills_the_dots(qapp_ready):
    """The folder's dots fill when the (late) profile lands — rebuild parity.

    The selector's answer arrives after the cards exist, and the landing path
    calls ``widget.refresh_cards(items)``; a rebuilt card must read the same
    live slot (never a value cached on the widget).
    """
    item = _item(axes=FREE_SCORES)
    gv = _live_grid(None, item=item)
    assert not tuple(getattr(_card(gv, item), "_gallery_dot_colors", ()) or ()), (
        "a card built BEFORE the profile landed already showed dots"
    )

    gv._gallery_widget._owner_for_triage().state.ai_profile = _ai_profile()
    gv.refresh_cards([item])
    card = _card(gv, item)
    assert len(tuple(getattr(card, "_gallery_dot_colors", ()) or ())) == len(
        FREE_AXES
    ), "the refresh did not pick up the freshly stored AI profile"
    gv.deleteLater()


def test_an_idle_card_with_nothing_measured_still_paints_no_dots(qapp_ready):
    """The two-phase rule is untouched: measured dots, or nothing at all.

    The judge named the axes but this item has no scorecard yet and no analysis
    is in flight, so the asked set is a LIE as an affordance (owner rule
    2026-10-22) — a card must stay empty rather than show six pending greys.
    """
    item = _item()  # no analysis at all, nothing running
    gv = _live_grid(_ai_profile(), item=item)
    card = _card(gv, item)
    assert tuple(getattr(card, "_gallery_dot_colors", ()) or ()) == (), (
        "an idle, unmeasured card painted placeholder dots on the live path"
    )
    gv.deleteLater()


def test_the_ai_card_never_dots_a_local_detector_number(qapp_ready):
    """Isolation: the AI card reads the judge, never ``item.metrics``.

    The item carries BOTH a local metric blob and the judge's scorecard. Only
    the judge's axes may be dotted: a local-only axis has no AI record, and the
    free axes carry the AI numbers even though the detectors know them not.
    """
    axes = dict(FREE_SCORES)
    item = _item(
        axes=axes,
        metrics={"sharpness": 320.0, "noise": 0.9, "white_balance": 0.5},
    )
    gv = _live_grid(_ai_profile(), item=item)
    card = _card(gv, item)

    infos = tuple(getattr(card, "_gallery_dot_infos", ()) or ())
    labels = [label for label, _score in infos]
    assert len(labels) == len(FREE_AXES), (
        f"the AI card mixed local detector axes into its dots: {labels}"
    )
    assert not any("Sharpness" in label for label in labels), (
        f"a local detector axis reached the AI card: {labels}"
    )
    assert [score for _label, score in infos] == [axes[n] for n in FREE_AXES]
    gv.deleteLater()
