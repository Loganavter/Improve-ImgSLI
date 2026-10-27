"""The center band separator is draggable but does not advertise it.

Owner report (2026-10-27): hovering the gallery's center splitter switched the
cursor to ``SplitHCursor`` and popped "Drag to resize series panes". Dragging is
still wanted; the *affordance* (cursor shape + tooltip) is not — the handle must
read as inert chrome.

Falsification (pre-fix, ``63eae8d``): ``_BandSeparatorHandle.__init__`` called
``setCursor(Qt.CursorShape.SplitHCursor)`` and installed the localized
``image_gallery.grid.resize_tooltip``. Both halves of
``test_separator_handle_hides_drag_affordance`` fail there (SplitH cursor +
non-empty tooltip) and pass after the change.

The second test is the guard against "fixing" this by disabling drag: press →
move past half a stride must still step the split one column left and re-anchor
``_press_x``.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(n: int, prefix: str = "img") -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{prefix}-{i:02d}.png"), mtime_ns=i + 1)
        for i in range(n)
    ]


def _banded_gallery(qtbot):
    """Wide, visible gallery with a live center separator handle."""
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1900, 900)
    w.show()
    items = _items(10)
    w.rebuild_grid(items)
    qtbot.wait(400)  # let the 150ms adapt timer reflow after show+resize
    gv = w._grid_view
    gv.set_series([items[:8]], hub_names=["HUB-A"], collapsed={})
    assert gv._band_state is not None
    sep = gv._band_separator
    assert sep is not None
    return w, gv, sep


def _mouse(ev_type, global_x: int, global_y: int, buttons) -> QMouseEvent:
    return QMouseEvent(
        ev_type,
        QPointF(4.0, 10.0),
        QPointF(float(global_x), float(global_y)),
        Qt.MouseButton.LeftButton,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def test_separator_handle_hides_drag_affordance(qtbot) -> None:
    """No SplitH cursor, no resize tooltip — the splitter must not advertise itself."""
    _, _, sep = _banded_gallery(qtbot)
    assert sep.cursor().shape() != Qt.CursorShape.SplitHCursor
    assert sep.toolTip() == ""


def test_separator_handle_drag_still_resizes_left_band(qtbot) -> None:
    """Drag survives the affordance removal: press → move steps the split."""
    _, gv, sep = _banded_gallery(qtbot)
    left = int(gv._band_state[0])
    assert left > 2, "need room to shrink the left band"
    stride = int(gv._grid_stride_px())
    assert stride > 0

    sep.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, 500, 400, Qt.MouseButton.LeftButton))
    assert sep._press_x == 500

    # Sub-half-stride jitter is a no-op, exactly as before.
    sep.mouseMoveEvent(
        _mouse(QEvent.Type.MouseMove, 500 + max(1, stride // 4), 400, Qt.MouseButton.LeftButton)
    )
    assert gv._band_state is not None and int(gv._band_state[0]) == left

    # One full stride left shrinks the left band by one column and re-anchors.
    sep.mouseMoveEvent(
        _mouse(QEvent.Type.MouseMove, 500 - stride, 400, Qt.MouseButton.LeftButton)
    )
    assert gv._band_state is not None and int(gv._band_state[0]) == left - 1
    assert sep._press_x == 500 - stride

    sep.mouseReleaseEvent(
        _mouse(QEvent.Type.MouseButtonRelease, 500 - stride, 400, Qt.MouseButton.NoButton)
    )
    assert sep._press_x is None
