"""P2 — an axis inside the noise floor carries no weight and says so on screen.

``plan-gallery-ai-judgement-2026-10-21`` §P2 / verified defect **J4** against
invariant **M3** ("discriminating"): on the live 6-variant cel-art folder the
model answered ``exposure = 82`` for five of six cards and
``sharpness ∈ {68,74,78}``, yet every measured axis fed the rank mean and every
Quick Look row rendered as a bare percentage that ranked nothing.

Falsification story:

- **rank** — a zero-spread axis (``exposure`` identical on both variants) must
  not decide the order. The fixture is built so the un-suppressed aggregate
  *inverts* the result: both items cap to ``RANK_WORST_AXIS_SLACK`` on the
  constant axis and the order degrades to ``str(path)``, while the salience-
  filtered order puts the genuinely sharper variant first.
- **guard** — when the floor cannot separate anything (every axis inside it) the
  order must stay measured, not silently become alphabetical: suppression is a
  weight decision, never a reason to drop the only measurements there are.
- **rows** — the row is KEPT and shows the reason ("does not separate these
  variants"), not a percentage; the axis that does separate keeps its number.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.services.rank_fusion import (
    INSIDE_NOISE,
    axis_salience,
    item_quality,
    rank_series,
)
from tabs.image_gallery.ui.quick_look import QuickLookOverlay
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label as _QlLabel
from sli_ui_toolkit.widgets import Text as _QlText


def _item(name: str, **metrics) -> SimpleNamespace:
    return SimpleNamespace(path=Path(f"/gallery/{name}"), metrics=dict(metrics))


# ---------------------------------------------------------------------------
# rank: an axis whose spread is inside the floor carries no weight
# ---------------------------------------------------------------------------


def test_a_zero_spread_axis_cannot_decide_the_order() -> None:
    # ``exposure=0.0`` scores 0 on both variants (``metric_scores._exposure``),
    # so the axis is measured, constant, and — being the worst axis — caps both
    # aggregates to RANK_WORST_AXIS_SLACK. Weighting it ties the series and the
    # order falls back to str(path) ("a.png" first), which is wrong: z.png is the
    # sharper variant by 5 points.
    z = _item("z.png", sharpness=400.0, exposure=0.0)  # sharpness 100
    a = _item("a.png", sharpness=380.0, exposure=0.0)  # sharpness 95
    members = [a, z]

    verdicts = axis_salience(
        [{"sharpness": 95, "exposure": 0}, {"sharpness": 100, "exposure": 0}],
        noise_floor=1.0,
    )
    assert verdicts["exposure"] == INSIDE_NOISE
    assert verdicts["sharpness"] != INSIDE_NOISE

    ranks = rank_series(members, mode="camera")
    assert ranks[str(z.path)] == 1, (
        "a constant axis decided the order: the sharper variant must win, not "
        f"the alphabetically first one ({ranks})"
    )

    # The exclusion is load-bearing, not cosmetic: with the constant axis
    # weighted both variants cap to the same aggregate and tie.
    assert item_quality(z, mode="camera") == item_quality(a, mode="camera"), (
        "the fixture no longer reproduces the defect — the constant axis must be "
        "the worst axis and cap both items equally"
    )


def test_suppression_never_degrades_the_order_to_path_order() -> None:
    """Every axis inside the floor → nothing is suppressed (one rule, both paths).

    A series whose whole spread is inside the floor would otherwise have no
    aggregate at all and rank by ``str(path)`` — a fabricated authority. The
    order stays measured (a tie is still a measurement).
    """
    members = [
        _item("a.png", sharpness=200.0),  # sharpness 50
        _item("b.png", sharpness=200.0),  # 50
        _item("c.png", sharpness=204.0),  # 51
    ]
    ranks = rank_series(members, mode="camera")
    assert ranks["/gallery/c.png"] == 1, (
        "the only axis in the series is inside the floor, so suppression emptied "
        f"the aggregate and the order became alphabetical ({ranks})"
    )


# ---------------------------------------------------------------------------
# the live J4 shape on the AI domain: 8 offered axes, 3 that separate
# ---------------------------------------------------------------------------


def test_the_live_flat_axes_are_not_offered_to_the_ranker() -> None:
    """The 2026-10-21 folder: only the axes with a real spread reach the model.

    Live: ``exposure`` 82 on five of six cards, ``sharpness ∈ {68,74,78}`` — both
    inside the model's own 12–23-point sampling noise — while ``noise`` moved
    across the series. Pre-P2 all three (plus the rest of the 8-axis camera
    profile) were sent to the ranker, so the order was decided by numbers that
    move more between two samples of ONE picture than between the variants.
    """
    from tabs.image_gallery.models import AiAnalysisResult
    from tabs.image_gallery.services.jev_client import build_measured_vector

    exposures = [82, 82, 82, 82, 82, 79]
    sharpness = [68, 74, 78, 70, 72, 76]
    noise = [20, 40, 60, 80, 30, 90]
    members = []
    for index, (exp, sharp, noise_score) in enumerate(
        zip(exposures, sharpness, noise), start=1
    ):
        item = GalleryItem(path=Path(f"/gallery/live_{index}.png"), mtime_ns=0)
        item.analysis = AiAnalysisResult(
            description="",
            tags=(),
            model="m",
            analyzed_at_iso="t",
            axes={"exposure": exp, "sharpness": sharp, "noise": noise_score},
        )
        members.append(item)

    profile = MetricProfile(
        axis_ids=("sharpness", "exposure", "noise"), mode="camera", source="vlm"
    )
    vector = build_measured_vector(
        members, mode="camera", domain="ai", profile=profile
    )

    offered = {axis for entry in vector["items"] for axis in entry["scores"]}
    assert offered == {"noise"}, (
        "the flat axes were offered to the ranker: the model is asked to order "
        f"these variants on constants (offered {sorted(offered)})"
    )


# ---------------------------------------------------------------------------
# rows: the reason, not a bare number — and the row is not removed
# ---------------------------------------------------------------------------


def _qlabels(widget):
    return widget.findChildren(_QlLabel) + widget.findChildren(_QlText)


def _row_texts(overlay) -> list[str]:
    return [lbl.text() for row in overlay._metric_rows for lbl in _qlabels(row)]


def _show(qtbot, item, series, *, profile):
    parent = QWidget()
    qtbot.addWidget(parent)
    overlay = QuickLookOverlay(parent)
    overlay._parity_test_parent = parent  # strong ref keeps the C++ tree alive
    owner = SimpleNamespace(
        _judgment_domain="algorithms",
        state=SimpleNamespace(
            mode=Mode.CAMERA,
            source_path=None,
            series=[list(series)],
            items=list(series),
            judgment_domain="algorithms",
            metric_profile=profile,
        ),
    )
    overlay.show_for(item, owner)
    parent.resize(1280, 800)
    parent.show()
    QApplication.processEvents()
    return overlay


def test_an_inside_noise_axis_is_rendered_with_its_reason(qtbot) -> None:
    """Two axes: one separates the series, one is constant → reason row, kept."""
    profile = MetricProfile(
        axis_ids=("sharpness", "exposure"), mode="camera", source="vlm"
    )
    a = GalleryItem(
        path=Path("/gallery/row_a.png"),
        mtime_ns=1,
        rank=2,
        metrics={"sharpness": 380.0, "exposure": 0.5},
    )
    z = GalleryItem(
        path=Path("/gallery/row_z.png"),
        mtime_ns=1,
        rank=1,
        metrics={"sharpness": 400.0, "exposure": 0.5},
    )
    overlay = _show(qtbot, z, [a, z], profile=profile)
    try:
        texts = _row_texts(overlay)
        reasons = [
            t for t in texts
            if "не различает" in t or "does not separate" in t
        ]
        assert len(reasons) == 1, (
            "the constant axis must be rendered with its reason, not a bare "
            f"number; rows were {texts}"
        )
        assert "0%" not in reasons[0], f"a reason row never carries a percentage: {reasons[0]}"
        # The row is KEPT (owner default D3: annotate, never remove) ...
        assert len(overlay._metric_rows) == 2, (
            f"both profile axes keep a row, got {len(overlay._metric_rows)}"
        )
        # ... and the axis that DOES separate the series keeps its number.
        assert any("%" in t for t in texts), (
            f"the discriminating axis lost its percentage: {texts}"
        )
    finally:
        overlay.hide()
