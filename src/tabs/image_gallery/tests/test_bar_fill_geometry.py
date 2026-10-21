"""Bar fills track fraction after layout settles (not floor, not first frame).

Regression: _set_painted_width pinned via setFixedWidth then lowered the
minimum to the floor — hint-less _FillBlock collapsed to the 4px minimum
on the next layout pass (full on the first frame, ~zero after, with the
<1px storm guard suppressing corrections). Width now rides on sizeHint.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import Mode
from tabs.image_gallery.ui.quick_look.bars import _BarWidget
from tabs.image_gallery.tests.test_quick_look_parity import (
    _item,
    _make_overlay,
    _qlabels,
    _show,
)


def _fills_by_title(ov):
    out = {}
    for row in ov._metric_rows:
        titles = [lbl.text() for lbl in _qlabels(row)]
        bars = row.findChildren(_BarWidget)
        if bars:
            out[tuple(titles)] = bars[0]
    return out


def test_fill_widths_match_fractions_after_settle(qtbot) -> None:
    item = _item(
        "p.png",
        metrics={"sharpness": 423.0, "exposure": 0.16, "clipping": 2.6, "noise": 0.54},
    )
    ov = _make_overlay(qtbot)
    _show(ov, item, [item], mode=Mode.CAMERA)
    QApplication.processEvents()
    QApplication.processEvents()
    fills = _fills_by_title(ov)
    sharp = next(b for titles, b in fills.items() if titles[0].startswith("Sharpness"))
    assert sharp._fraction == 1.0
    assert sharp._fill.width() == sharp.width()  # full, not the 4px floor
    for titles, bar in fills.items():
        if titles[0].startswith("Sharpness"):
            continue
        expect = int(bar.width() * bar._fraction)
        assert abs(bar._fill.width() - expect) <= 2
    ov.hide()


def test_fill_settled_synchronously_on_walk(qtbot) -> None:
    """Walk rebuild settles fills before the next paint (no lowered transient).

    Regression: rebuilt rows stayed hidden (no implicit show under an
    already-visible host), so bars laid out at a ~100px default and fills
    lagged one more pass — live: lowered values for ~2 frames after every
    image switch, then correct. No processEvents between _walk and the
    asserts: the first paint must already be right.
    """
    from tabs.image_gallery.models import Mode

    a = _item(
        "a.png",
        metrics={"sharpness": 400.0, "exposure": 0.5, "clipping": 1.0, "noise": 0.2},
    )
    b = _item(
        "b.png",
        metrics={"sharpness": 380.0, "exposure": 0.6, "clipping": 1.2, "noise": 0.3},
    )
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b], mode=Mode.CAMERA)
    QApplication.processEvents()
    QApplication.processEvents()
    settled_w = next(
        bar.width() for row in ov._metric_rows for bar in row.findChildren(_BarWidget)
    )
    assert settled_w > 100
    ov._walk(1)
    # No processEvents: first frame after the switch.
    for row in ov._metric_rows:
        for bar in row.findChildren(_BarWidget):
            assert bar.width() == settled_w
            assert abs(bar._fill.width() - int(bar.width() * bar._fraction)) <= 2
    ov.hide()


def test_dual_bar_settled_synchronously_on_walk(qtbot) -> None:
    """Same walk-settle guarantee for the fidelity dual restored/invented bar."""
    from tabs.image_gallery.models import Mode
    from tabs.image_gallery.ui.quick_look.bars import _DualRestoredInventedBar

    a = _item(
        "a.png",
        metrics={"ssim": 0.93, "hf_ratio": 0.18, "delta_e": 1.2, "upscale_factor": 2},
    )
    b = _item(
        "b.png",
        metrics={"ssim": 0.88, "hf_ratio": -0.1, "delta_e": 3.1, "upscale_factor": 2},
    )
    ov = _make_overlay(qtbot)
    _show(ov, a, [a, b], mode=Mode.FIDELITY)
    QApplication.processEvents()
    QApplication.processEvents()
    ov._walk(1)
    duals = [d for row in ov._metric_rows for d in row.findChildren(_DualRestoredInventedBar)]
    assert duals
    for dual in duals:
        total = dual.width()
        assert total > 100
        assert abs(dual._left.width() + dual._right.width() - total) <= 2
    ov.hide()


def test_fill_follows_resize_without_ratchet(qtbot) -> None:
    """Grow→shrink restores widths (floor minimum, no sticky pin)."""
    item = _item("p.png", metrics={"sharpness": 423.0})
    ov = _make_overlay(qtbot)
    _show(ov, item, [item], mode=Mode.CAMERA)
    QApplication.processEvents()
    QApplication.processEvents()
    fills = _fills_by_title(ov)
    bar = next(iter(fills.values()))
    w0, fill0 = bar.width(), bar._fill.width()
    assert fill0 == w0
    bar.resize(w0 + 120, bar.height())
    QApplication.processEvents()
    QApplication.processEvents()
    assert bar._fill.width() == bar.width()
    bar.resize(w0, bar.height())
    QApplication.processEvents()
    QApplication.processEvents()
    assert bar.width() == w0
    assert bar._fill.width() == w0
    ov.hide()
