"""Marquee band behavior contract (Lane A, phase A1).

Pins the gallery marquee's update/finish plumbing against the stable public
API (``on_rect_update`` / ``on_rect_finish`` / ``event_filter`` /
``host_mouse_press``) so the A2 in-paint refactor can prove no semantic
drift: these tests pass on the overlay path AND on the in-paint path.

Mapping/pixel tests for the new path live in the A2 section below (they
exercise ``MarqueeState``/``MarqueeHost`` content-space identity and only
pass post-refactor).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent

from tabs.image_gallery.ui import marquee as _marquee


def _card(geom: QRect):
    return SimpleNamespace(geometry=lambda: QRect(geom))


def _view():
    applied: list[set] = []
    cards = {
        "a.png": _card(QRect(10, 10, 100, 100)),
        "b.png": _card(QRect(200, 10, 100, 100)),
    }
    view = SimpleNamespace(
        _items=[SimpleNamespace(path=Path("a.png")), SimpleNamespace(path=Path("b.png"))],
        _marquee_additive=False,
        _marquee_base=set(),
        _owner=None,
        owner=None,
        _on_marquee_preview=None,
        apply_selection=lambda paths: applied.append(set(paths)),
    )
    view.card_for = lambda p: cards.get(str(p))
    return view, applied


def _owner_view():
    """View delegating commits to an owner (production shape)."""
    painted: list[set] = []
    grid = SimpleNamespace(apply_selection=lambda paths: painted.append(set(paths)))
    state = SimpleNamespace(selected_paths=set())
    owner = SimpleNamespace(state=state, grid_view=grid)
    view = SimpleNamespace(
        _items=[SimpleNamespace(path=Path("a.png")), SimpleNamespace(path=Path("b.png"))],
        _marquee_additive=False,
        _marquee_base=set(),
        _owner=owner,
        owner=None,
        _on_marquee_preview=None,
        apply_selection=lambda paths: painted.append(set(paths)),
    )
    view.card_for = lambda p: None  # force fixed-grid fallback path? no — no cards
    return view, owner, painted


def test_update_dispatches_preview_paths() -> None:
    view, applied = _view()
    _marquee.on_rect_update(view, QRect(0, 0, 150, 150))  # hits card A only
    assert len(applied) == 1
    assert {str(p) for p in applied[0]} == {"a.png"}


def test_update_additive_unions_base() -> None:
    view, applied = _view()
    view._marquee_additive = True
    view._marquee_base = {Path("b.png")}
    _marquee.on_rect_update(view, QRect(0, 0, 150, 150))  # hits A; preview = base | hit
    assert len(applied) == 1
    assert {str(p) for p in applied[0]} == {"a.png", "b.png"}


def test_finish_commits_via_owner_with_paths_and_flag() -> None:
    view, owner, painted = _owner_view()
    # Owner path needs live card geometry: stub card_for via fixed grid is
    # bypassed here — give the view real card geometry instead.
    cards = {
        "a.png": _card(QRect(10, 10, 100, 100)),
        "b.png": _card(QRect(200, 10, 100, 100)),
    }
    view.card_for = lambda p: cards.get(str(p))
    view._marquee_additive = False
    _marquee.on_rect_finish(view, QRect(0, 0, 350, 150))  # hits A+B
    assert {str(p) for p in owner.state.selected_paths} == {"a.png", "b.png"}


def test_finish_empty_non_additive_clears_owner() -> None:
    """COMMIT-EMPTY: shrink-to-empty replaces with the hit set (empty)."""
    view, owner, painted = _owner_view()
    owner.state.selected_paths = {Path("a.png")}
    view._marquee_additive = False
    _marquee.on_rect_finish(view, QRect())
    assert set(owner.state.selected_paths) == set()


def test_finish_empty_additive_keeps_selection() -> None:
    view, owner, painted = _owner_view()
    owner.state.selected_paths = {Path("a.png")}
    view._marquee_additive = True
    _marquee.on_rect_finish(view, QRect())
    assert {str(p) for p in owner.state.selected_paths} == {"a.png"}


def test_tiny_drag_finishes_empty_non_additive() -> None:
    """1x1 band over empty space hits nothing → non-additive commit clears."""
    view, owner, painted = _owner_view()
    cards = {
        "a.png": _card(QRect(10, 10, 100, 100)),
        "b.png": _card(QRect(200, 10, 100, 100)),
    }
    view.card_for = lambda p: cards.get(str(p))
    owner.state.selected_paths = {Path("a.png")}
    view._marquee_additive = False
    _marquee.on_rect_finish(view, QRect(0, 0, 1, 1))
    assert set(owner.state.selected_paths) == set()


def _mouse_event(etype, local: QPoint, global_pos: QPoint, button, buttons):
    return QMouseEvent(
        etype,
        QPointF(local),
        QPointF(global_pos),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


def test_release_passes_through_while_finishing(qtbot) -> None:
    """Hover-loss contract: LeftButton release returns False (pass-through),
    moves are consumed while dragging. Holds on both gesture generations.
    """
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    view = GalleryGridView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.wait(50)
    host = view.items_host
    origin = QPoint(host.width() - 30, host.height() - 30)
    assert host.childAt(origin) is None
    press = _mouse_event(
        QEvent.Type.MouseButtonPress, origin, host.mapToGlobal(origin),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
    )
    assert _marquee.host_mouse_press(view, press) is True
    gesture = view._marquee_gesture
    assert gesture is not None
    assert bool(getattr(gesture, "active", False)) is True

    moved_at = QPoint(origin.x() - 200, origin.y() - 100)
    move = _mouse_event(
        QEvent.Type.MouseMove, moved_at, host.mapToGlobal(moved_at),
        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
    )
    assert gesture.eventFilter(host, move) is True  # consumed while dragging

    release = _mouse_event(
        QEvent.Type.MouseButtonRelease, moved_at, host.mapToGlobal(moved_at),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
    )
    assert gesture.eventFilter(host, release) is False  # pass-through, still finishes


# -- A2: in-paint path (content-space identity + host pixels) ----------------

def _detached_state(origin=None):
    """MarqueeState without widgets: pure mapping, no QApplication needed."""
    from PySide6.QtCore import QObject
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.widgets import MarqueeState

    updated: list[QRect] = []
    finished: list[QRect] = []
    holder = QObject()
    host = SimpleNamespace(set_band_rect=lambda rect: None)
    state = MarqueeState(
        host,  # type: ignore[arg-type]
        parent=holder,
        on_update=lambda r: updated.append(QRect(r)),
        on_finish=lambda r: finished.append(QRect(r)),
    )
    state._test_holder = holder  # keep the QObject parent alive
    return state, updated, finished


def test_state_band_is_content_space_identity() -> None:
    """No window round-trip: band == QRect(origin, pos).normalized()."""
    from PySide6.QtCore import QPoint

    state, updated, _ = _detached_state()
    origin = QPoint(30, 40)
    assert state.start(origin) is True
    assert state.active is True
    assert state.update_at(QPoint(120, 10)) == QRect(origin, QPoint(120, 10)).normalized()
    assert state.update_at(QPoint(150, 90)) == QRect(30, 40, 121, 51)
    # Toolkit semantics: update_at emits too (eventFilter path relies on it).
    assert updated == [
        QRect(30, 40, 1, 1),  # start() emits the degenerate band
        QRect(origin, QPoint(120, 10)).normalized(),
        QRect(30, 40, 121, 51),
    ]


def test_state_tiny_finish_is_empty_rect() -> None:
    """Degenerate drags finish as QRect() (same min_drag_px=3 rule).

    Toolkit semantics: finish is single-shot (clears the origin, like the
    eventFilter path) — every finish below starts a fresh drag first.
    """
    from PySide6.QtCore import QPoint

    state, _, finished = _detached_state()
    assert state.start(QPoint(10, 10)) is True
    assert state.finish_at(QPoint(10, 10)) == QRect()  # 1x1 degenerate
    assert state.start(QPoint(10, 10)) is True
    assert state.finish_at(QPoint(11, 11)) == QRect()  # 2x2 still tiny
    assert state.start(QPoint(10, 10)) is True
    band = state.finish_at(QPoint(10, 30))  # 1px wide but 21 tall: not tiny
    assert not band.isEmpty() and (band.width(), band.height()) == (1, 21)


def test_state_cancel_clears_without_finish() -> None:
    from PySide6.QtCore import QPoint

    state, _, finished = _detached_state()
    assert state.start(QPoint(5, 5)) is True
    state.cancel()
    assert state.active is False
    assert finished == []


def test_host_band_pixel_at_cursor(qtbot) -> None:
    """Offscreen: band paints accent-blended pixels inside the set rect."""
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    view = GalleryGridView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.wait(50)
    host = view.items_host
    band = QRect(100, 100, 200, 120)
    host.set_band_rect(QRect(band))
    assert host.band_rect == band
    img = host.grab().toImage()
    inside = img.pixelColor(band.center()).getRgb()
    outside = img.pixelColor(5, 5).getRgb()
    assert inside != outside


def test_host_shrink_clears_exposed_region(qtbot) -> None:
    """Big→small: the exposed region returns to substrate (no stale band)."""
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    view = GalleryGridView()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.wait(50)
    host = view.items_host
    host.set_band_rect(QRect(100, 100, 300, 200))
    qtbot.wait(20)
    small = QRect(100, 100, 60, 50)
    host.set_band_rect(QRect(small))
    assert host.band_rect == small
    img = host.grab().toImage()
    exposed = img.pixelColor(350, 250).getRgb()  # inside big, outside small
    substrate = img.pixelColor(5, 5).getRgb()
    assert exposed == substrate
    assert img.pixelColor(small.center()).getRgb() != substrate


def test_apply_selection_cold_sweep_paints_nothing_unselected(qtbot) -> None:
    """First preview sweep must not repaint every card (~26ms drag-start stall).

    Cards without a stamp are already visually unselected: stamping them
    without painting keeps the cold sweep free. Only genuinely selected
    cards may be touched.
    """
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    view = GalleryGridView()
    qtbot.addWidget(view)

    calls: list = []

    class _StubCard:
        def set_override_bg_color(self, color) -> None:
            calls.append(("bg", color))

        def set_bg_locked(self, locked: bool) -> None:
            calls.append(("lock", locked))

    stubs = {"a.png": _StubCard(), "b.png": _StubCard()}
    view._cards_by_path = stubs
    view.apply_selection(set())
    assert calls == []
    assert all(
        getattr(c, "_gallery_sel_applied", None) is not None for c in stubs.values()
    )
    view.apply_selection({Path("a.png")})
    painted = [c for op, c in calls if op == "bg" and c is not None]
    assert len(painted) == 1
