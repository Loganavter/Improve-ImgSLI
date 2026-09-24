"""W12 W-C: empty-state single-flight open + expanding drop zone.

Regression: one LMB click on the DnD zone opened TWO folder pickers
sequentially (``_open_button.clicked`` + the zone ``mousePressEvent``
override both emitted ``openRequested`` for a single click). The zone
also had a fixed minimum height instead of filling available space.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QSizePolicy

from tabs.image_gallery.ui.states import GalleryEmptyState


def _press(widget, button: Qt.MouseButton):
    ev = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        widget.rect().center().toPointF(),
        button,
        button,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(ev)


def test_one_lmb_click_emits_open_once(qtbot) -> None:
    """Both click paths firing together collapse to exactly one emit."""
    state = GalleryEmptyState()
    qtbot.addWidget(state)
    count = []
    state.openRequested.connect(lambda: count.append(1))

    # Simulate the double path: zone press AND button click for one LMB click.
    _press(state._drop_label, Qt.MouseButton.LeftButton)
    try:
        state._open_button.click()
    except Exception:
        state._open_button.clicked.emit()

    assert len(count) == 1


def test_rapid_double_request_single_flights(qtbot) -> None:
    """Two rapid _request_open calls emit once; expiry re-arms."""
    state = GalleryEmptyState()
    qtbot.addWidget(state)
    count = []
    state.openRequested.connect(lambda: count.append(1))

    state._request_open()
    state._request_open()
    assert len(count) == 1

    # After the window expires, a new click emits again.
    state._last_open_emit -= GalleryEmptyState._OPEN_SINGLE_FLIGHT_S + 0.1
    state._request_open()
    assert len(count) == 2


def test_right_click_does_not_request_open(qtbot) -> None:
    """Non-LMB presses never emit openRequested."""
    state = GalleryEmptyState()
    qtbot.addWidget(state)
    count = []
    state.openRequested.connect(lambda: count.append(1))

    _press(state._drop_label, Qt.MouseButton.RightButton)
    assert count == []


def test_drop_zone_expands_to_fill(qtbot) -> None:
    """Zone fills available space: expanding policy, no fixed height."""
    state = GalleryEmptyState()
    qtbot.addWidget(state)
    zone = state._drop_label

    assert zone.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
    assert zone.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    # No fixed-height floor from the old 180px minimum.
    assert zone.minimumHeight() < 180
    assert zone.maximumHeight() >= 10000 or zone.maximumHeight() == 16777215

    # Layout gives the zone stretch so it takes free vertical space.
    layout = state.layout()
    idx = layout.indexOf(zone)
    assert idx >= 0
    assert layout.stretch(idx) >= 1
