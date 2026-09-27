"""Empty-state single-flight open + expanding drop zone.

Zone click does NOT open the folder dialog — only the Open Folder button.
Single-flight collapses rapid button double-clicks into one emit. The zone
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
    """Zone is drop-only: LMB/RMB presses never emit openRequested."""
    state = GalleryEmptyState()
    qtbot.addWidget(state)
    count = []
    state.openRequested.connect(lambda: count.append(1))

    # Zone click must NOT request open — drag&drop only (no button anymore).
    _press(state._drop_label, Qt.MouseButton.LeftButton)
    assert count == []


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


def test_emptied_by_removals_shows_empty_view_text(qtbot) -> None:
    """Grid emptied by removals must not claim no folder is picked.

    Regression: reject on the last card showed S0 "Pick a folder…"
    although files stay on disk — the view just has nothing to show.
    """
    from pathlib import Path

    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.widget import ImageGalleryWidget

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    w.rebuild_grid([item])
    w.rebuild_grid([])
    assert w._empty_state._drop_label.get_original_text() == "No images in view."
    assert w._empty_label.get_original_text() == "No images in view."
    # Compat shim is never shown: it has no layout slot and would pin at (0,0).
    assert not w._empty_label.isVisible()


def test_pristine_empty_shows_pick_folder_text(qtbot) -> None:
    """Never-opened grid keeps the default pick-a-folder message."""
    from tabs.image_gallery.widget import ImageGalleryWidget

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.rebuild_grid([])
    # Drop zone keeps its construction default (no translate in this context).
    assert w._empty_state._drop_label.get_original_text() == "Drop folder or images here"
    assert w._empty_label.get_original_text() == "Pick a folder to see images here."
    assert not w._empty_label.isVisible()


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


def test_scanning_hides_drop_zone(qtbot) -> None:
    """S1 shows spinner + count only — no DnD zone while loading/scanning."""
    state = GalleryEmptyState()
    qtbot.addWidget(state)
    state.set_state("scanning", 2, 4)
    assert not state._drop_label.isVisible()
    assert getattr(state, "_hint_label", None) is None
    assert getattr(state, "_open_button", None) is None
    assert state._spinner.isVisible()
    assert state._scanning_label.isVisible()
    assert "2/4" in state._scanning_label.text()
    # Back to empty restores the zone.
    state.set_state("empty")
    assert state._drop_label.isVisible()
    assert not state._spinner.isVisible()
