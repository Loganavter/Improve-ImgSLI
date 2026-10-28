"""Quick Look's metrics column must never arm a HORIZONTAL scrollbar.

Live bug (owner, 2026-10-27): opening Quick Look showed a horizontal scrollbar
in the metrics block for the first frames, then it vanished after the first
real layout. The column is width-fitted by construction (W5/W13 fit budget,
``metrics/rows.py``), so nothing legitimately overflows sideways.

Diagnosis (the internal notes on DEBUGGING ladder):

- **blast radius**: only the report column (``quicklook_right_scroll``); the
  gallery grid and the strip ride the same toolkit ``OverlayScrollArea``
  without the flash.
- **working sibling**: the strip scroller is built with
  ``widget_resizable=False`` and content that carries no width floor, so its
  horizontal range is 0 from the first pass. The report column differs in one
  input: its content widget (``quicklook_right_host``) had a GROW size policy
  (Expanding), so ``qSmartMinSize`` reported the host's own
  ``minimumSizeHint`` width (296px — the brief label's floor) as its minimum.
- **discriminator** (offscreen, before any event-loop turn): a QScrollArea is
  resized *after* its viewport, so the first pass sized the host at 296 inside
  the viewport's 100px default. The native horizontal range went ``0..196``
  and stayed armed, while the toolkit's floating bar (``custom_h_scrollbar``)
  is driven by that NATIVE range — it ignores
  ``setHorizontalScrollBarPolicy(AlwaysOff)``, which only hides the stock bar.
  The opening frame therefore painted a horizontal thumb for an overflow that
  the first real layout (viewport 329) collapses to 0.
- **fix** (app side, no toolkit change): the host's horizontal policy is
  ``Ignored``, so its horizontal minimum is 0 and the scroll area can always
  shrink it into whatever viewport it is given — the range stays 0 in every
  frame, so the bar is never armed. The 296px column floor stays on the SCROLL
  AREA (``build.py`` W13), not on the host, so the design width is unchanged.

The assertions below are the invariant, not the symptom: the horizontal range
is 0 before the first layout tick, after it, at other window sizes, and while
the vertical bar is genuinely needed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.services.metric_profile import MetricProfile
from tabs.image_gallery.ui.quick_look import QuickLookOverlay


def _item(name: str) -> GalleryItem:
    return GalleryItem(
        path=Path(f"/gallery/{name}"),
        mtime_ns=1,
        rank=1,
        metrics={
            "ssim": 0.93,
            "detail_gain": 1.1,
            "sharpness": 150.0,
            "noise": 0.2,
            "exposure": 0.5,
            "clipping": 0.4,
        },
    )


def _open(qtbot, item, *, size=(1280, 800)):
    """Build the report column exactly as the panel opens (no layout tick yet).

    ``show_for`` is the pre-show build the overlay runs (rows are rebuilt into
    ``quicklook_right_host``); ``show()`` is what the panel does next. The
    caller drives the event loop — the assertions here are about the state
    BEFORE and AFTER the first layout pass.
    """
    profile = MetricProfile(
        axis_ids=("ssim", "detail_gain", "sharpness", "noise"),
        mode="fidelity",
        source="vlm",
    )
    parent = QWidget()
    qtbot.addWidget(parent)
    overlay = QuickLookOverlay(parent)
    overlay._parity_test_parent = parent  # strong ref keeps the C++ tree alive
    owner = SimpleNamespace(
        _judgment_domain="algorithms",
        state=SimpleNamespace(
            mode=Mode.FIDELITY,
            source_path=None,
            series=[list([item])],
            items=list([item]),
            judgment_domain="algorithms",
            algorithms_profile=profile,
            ai_profile=None,
        ),
    )
    overlay.show_for(item, owner)
    scroll = overlay._content.findChild(QWidget, "quicklook_right_scroll")
    assert scroll is not None, "the report column's scroller is gone (fixture drift)"
    return overlay, parent, scroll, size


def _pump(times: int = 20) -> None:
    for _ in range(times):
        QApplication.processEvents()


def test_the_report_column_never_arms_a_horizontal_scrollbar(qtbot):
    """No frame — pre-layout or settled — may put a horizontal bar in the column."""
    overlay, parent, scroll, size = _open(qtbot, _item("hscroll_open.png"))
    try:
        host = overlay._report_host
        pre_layout = scroll.horizontalScrollBar()
        assert pre_layout.maximum() == 0, (
            "the metrics column is wider than its viewport BEFORE the first "
            f"layout tick ({pre_layout.maximum()}px of overflow at viewport "
            f"{scroll.viewport().width()}px): the toolkit overlay horizontal "
            "bar arms from this range and the opening frames paint it"
        )
        assert host.width() <= scroll.viewport().width(), (
            f"the report host does not fit its viewport ({host.width()} > "
            f"{scroll.viewport().width()}) — the column can be pushed sideways"
        )
        # The mechanism, so a future edit cannot silently restore the flash by
        # giving the host a width floor again (Ignored ⇒ horizontal minimum 0,
        # the viewport is the only width authority).
        assert host.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored, (
            "the report host must stay horizontally Ignored — a grow policy "
            "hands the scroll area the host's own minimumSizeHint as its "
            "lower bound (the 296px brief floor) and the pre-layout viewport "
            f"is narrower than that: {host.sizePolicy().horizontalPolicy()}"
        )

        parent.resize(*size)
        parent.show()
        _pump()

        assert scroll.horizontalScrollBar().maximum() == 0, (
            "the settled column still overflows sideways "
            f"({scroll.horizontalScrollBar().maximum()}px)"
        )
        assert not scroll.custom_h_scrollbar.isVisible(), (
            "the overlay horizontal bar is live in a width-fitted column"
        )

        # Other window sizes: the card resizes, the invariant holds.
        for width, height in ((1040, 680), (1100, 700), (900, 620), (1280, 800)):
            parent.resize(width, height)
            _pump()
            assert scroll.horizontalScrollBar().maximum() == 0, (
                f"a {width}px-wide window armed the horizontal bar"
            )
            assert not scroll.custom_h_scrollbar.isVisible(), (
                f"a {width}px-wide window showed the horizontal bar"
            )

        # Vertical scrolling is NOT sacrificed: a genuinely short column still
        # scrolls, and its reserved gutter does not re-arm the horizontal axis.
        scroll.setFixedHeight(160)
        _pump()
        try:
            assert scroll.verticalScrollBar().maximum() > 0, (
                "the vertical axis stopped overflowing on a short column — the "
                "fit fix must not disable vertical scrolling"
            )
            assert scroll.custom_v_scrollbar.isVisible(), (
                "the vertical overlay bar did not appear on a short column"
            )
            assert scroll.horizontalScrollBar().maximum() == 0, (
                "the vertical bar's gutter narrowed the viewport and the column "
                "overflowed sideways again"
            )
            assert not scroll.custom_h_scrollbar.isVisible()
        finally:
            scroll.setMinimumHeight(0)
            scroll.setMaximumHeight(16777215)

        # Rows still lay out at the REAL column width (elision rides it).
        _pump()
        widths = {row.width() for row in overlay._metric_rows}
        assert widths == {overlay._report_host.width()}, (
            f"metric rows stopped tracking the column width: {widths} vs "
            f"{overlay._report_host.width()}"
        )
    finally:
        overlay.hide()
