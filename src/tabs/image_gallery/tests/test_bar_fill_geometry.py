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
    _show,
)


def _fills_by_title(ov):
    from sli_ui_toolkit.widgets import Label as _L

    out = {}
    for row in ov._metric_rows:
        titles = [lbl.text() for lbl in row.findChildren(_L)]
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
