"""Quick Look keyboard navigation — the toolkit's row section (nav_section.py).

The panel is a ``ToolbarRowsSection`` over the two rows it already has — the
filmstrip (``overlay._strip_row``) and the action bar (``overlay._action_bar``):

* ``←``/``→`` move the focus ring within the row, the picture follows on
  ``Enter`` (the toolkit ``Button``'s own activation), so a series can be read
  without re-decoding an image per keystroke;
* ``↓``/``↑`` cross between the rows, so the action row's three buttons are
  keyboard-reachable;
* the cursor is the app's ONE focus vocabulary (the toolkit ring on the thumb
  ``Button``) — there is no painted marker, no index attribute and no zone
  memory, and nothing here claims Return/Enter;
* a strip rebuild keeps the ring on the item it was on, and ``↑``/``↓`` at the
  panel's edge keep focus inside the panel (the gallery grid behind the veil
  must never receive an arrow while the panel is open).

Four of these were live-reported on 2026-10-17 and are pinned individually
(no picture change on arrows; Enter shows once and leaves a working ring; all
three action buttons reachable; the ring lands on the thumb Button and not its
container). Each test below names the line whose removal turns it red — see the
``Falsified by:`` notes — because these run over the real overlay offscreen.

Runs offscreen (no Xvfb): the real ``QuickLookOverlay`` + the real
``NavigationManager``, keys delivered through ``QApplication.sendEvent`` to the
focused widget, so the whole manager → section → widget path is exercised.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection
from sli_ui_toolkit.widgets import Button

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.tests.test_quicklook_strip import (
    _make_overlay,
    _real_png,
    _show,
)
from tabs.image_gallery.ui.quick_look import nav_section as nav


@pytest.fixture(autouse=True)
def _restore_nav_modality():
    """Undo the app-wide input-modality flip every injected key causes.

    ``NavigationManager.eventFilter`` sets ``_last_input_keyboard`` on each
    KeyPress, which decides whether a later programmatic focus grant paints the
    keyboard ring. The grid's own keyboard test restores it for the same reason;
    without this, every test that follows this module inherits "keyboard mode".
    """
    manager = NavigationManager.get_instance()
    previous = getattr(manager, "_last_input_keyboard", False)
    yield
    manager._last_input_keyboard = previous


def _series(tmp_path, n: int = 4) -> list[GalleryItem]:
    """``n`` real items, ranked so every thumb also carries a rank pill."""
    paths = [_real_png(tmp_path, f"n{i}.png") for i in range(n)]
    return [GalleryItem(path=p, mtime_ns=i + 1, rank=i + 1) for i, p in enumerate(paths)]


def _open(qtbot, tmp_path, n: int = 4, current: int = 2):
    """A shown Quick Look panel with ``n`` items, the ring on ``current``.

    The window is up before ``show_for`` runs — the real ordering (a user opens
    the panel over a visible gallery window); ``_show``'s own parent-resize
    afterwards is a no-op then.
    """
    items = _series(tmp_path, n)
    overlay = _make_overlay(qtbot)
    parent = overlay.parentWidget()
    parent.resize(1280, 800)
    parent.show()
    QApplication.processEvents()
    _show(overlay, items[current], items)
    QApplication.processEvents()
    return overlay, items


def _press(key: Qt.Key) -> QWidget | None:
    """Deliver a real key press to the focused widget (manager path included)."""
    focused = QApplication.focusWidget()
    assert focused is not None, "nothing is focused — the test cannot drive the panel"
    QApplication.sendEvent(
        focused, QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    )
    QApplication.processEvents()
    return QApplication.focusWidget()


def _name(widget) -> str:
    return str(widget.objectName()) if widget is not None else "<none>"


def _wait_for_click(qtbot) -> None:
    """Strip thumbs defer their click to the ripple — wait it out."""
    from sli_ui_toolkit.widgets import get_ripple_duration_ms

    qtbot.wait(int(get_ripple_duration_ms()) + 200)
    QApplication.processEvents()


def _populate_calls(monkeypatch) -> list:
    """Record re-binds at the seam ``_switch`` / ``_walk`` actually call."""
    from tabs.image_gallery.ui.quick_look.overlay_parts import populate as populate_parts

    original = populate_parts._populate
    calls: list = []

    def _recorder(overlay, preserve_view: bool = False):
        calls.append(bool(preserve_view))
        return original(overlay, preserve_view=preserve_view)

    monkeypatch.setattr(populate_parts, "_populate", _recorder)
    return calls


class _NeighbourSection:
    """A stand-in for a page section registered above/below the panel."""

    def __init__(self, widget) -> None:
        self._widget = widget

    def owns(self, widget) -> bool:
        return widget is self._widget

    def navigate(self, key, widget) -> bool:
        return False

    def focus_first(self, ref_x=None, *, reason) -> bool:
        self._widget.setFocus(reason)
        return True

    def focus_last(self, ref_x=None, *, reason) -> bool:
        self._widget.setFocus(reason)
        return True


def test_the_panel_is_the_toolkit_rows_section_over_its_two_rows(qtbot, tmp_path) -> None:
    """No bespoke machinery: the registered section IS a ToolbarRowsSection.

    Falsified by: reverting ``nav_section.QuickLookNavSection`` to the
    hand-written cursor section — there is no ``section_of``/``rows`` then, and
    the row step the arrows use comes from the toolkit class below.
    """
    overlay, _items = _open(qtbot, tmp_path)
    section = nav.section_of(overlay)
    assert section is not None, "the visible panel must be a registered section"
    assert nav.rows(overlay) == [overlay._strip_row, overlay._action_bar]
    assert isinstance(section, ToolbarRowsSection)
    assert section.owns(nav.thumb_for_path(overlay, str(_items[0].path))) is True
    assert section.owns(overlay._close_btn) is False, (
        "only the two rows are claimed — not the whole panel"
    )
    overlay.hide()


def test_extra_keys_is_a_property_claiming_only_left_right(qtbot, tmp_path) -> None:
    """``←``/``→`` are opted back in; Return/Enter are left to the Button.

    Two live defects in one pin: a method-shaped ``extra_keys`` raised
    ``TypeError`` inside ``NavigationManager.eventFilter`` on every arrow
    (``key in getattr(spec, "extra_keys", frozenset())`` — the manager's own raw
    read), and a section that claims Enter steals the focused Button's own
    activation.
    """
    overlay, _items = _open(qtbot, tmp_path)
    section = nav.section_of(overlay)
    assert isinstance(type(section).extra_keys, property), (
        "readers iterate the raw attribute — a method breaks the event filter"
    )
    raw = getattr(section, "extra_keys", frozenset())  # the manager's exact read
    assert isinstance(raw, frozenset) and raw == frozenset(
        {Qt.Key.Key_Left, Qt.Key.Key_Right}
    ), raw
    assert Qt.Key.Key_Return not in raw and Qt.Key.Key_Enter not in raw
    assert Qt.Key.Key_Space not in raw
    overlay.hide()


def test_arrows_move_the_ring_and_never_rebind(qtbot, tmp_path, monkeypatch) -> None:
    """Report (a): arrowing the strip must not change the picture (Enter does)."""
    overlay, items = _open(qtbot, tmp_path)
    binds = _populate_calls(monkeypatch)
    assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[2].path)), (
        "the ring must open on the item already on screen"
    )

    focused = _press(Qt.Key.Key_Right)
    assert focused is nav.thumb_for_path(overlay, str(items[3].path)), _name(focused)
    assert overlay._current_idx == 2 and overlay._current_item.path == items[2].path
    assert binds == [], "an arrow must not re-bind the preview"

    focused = _press(Qt.Key.Key_Left)
    assert focused is nav.thumb_for_path(overlay, str(items[2].path)), _name(focused)
    assert binds == []
    overlay.hide()


def test_left_right_stop_at_the_row_edge_instead_of_wrapping(qtbot, tmp_path) -> None:
    """The toolkit's row step clamps at the edge; the panel does not wrap.

    The cursor stopped being an index with modulo arithmetic when the section
    became the toolkit row (``_focusable`` + ``items[cur + step]``, no wrap).
    Falsified by: reintroducing a wrapping index cursor.
    """
    overlay, items = _open(qtbot, tmp_path, current=0)
    for _ in range(3):
        _press(Qt.Key.Key_Left)
    assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[0].path))
    assert overlay._current_idx == 0, "the picture never moves on an arrow"
    overlay.hide()


def _churn_strip(overlay, items) -> None:
    """Force a FULL strip rebuild — the path that replaces the thumb widgets.

    The analysis pass re-stamps ranks, which mismatches the strip's fingerprint
    (``strip/helpers.py::_strip_fingerprint`` — the viewing index is deliberately
    excluded, so a plain walk takes the selection-only fast path and touches no
    widgets). The assertion keeps a test from silently falling back to that fast
    path and passing without exercising the snapshot/restore.
    """
    before_widgets = list(nav.strip_thumbs(overlay))
    assert before_widgets, "the strip must have thumbs to churn"
    items[-1].rank = (int(getattr(items[-1], "rank", 1) or 1) + 7)
    from tabs.image_gallery.services.rank_badge import stamp_badges

    stamp_badges(items)
    overlay._rebuild_strip()
    QApplication.processEvents()
    after = {id(w) for w in nav.strip_thumbs(overlay)}
    assert before_widgets and not ({id(w) for w in before_widgets} & after), (
        "this test needs the full rebuild path (thumb widgets replaced)"
    )


def test_enter_shows_the_focused_item_exactly_once(qtbot, tmp_path, monkeypatch) -> None:
    """Report (b): Enter shows the focused item once, then arrowing still works."""
    overlay, items = _open(qtbot, tmp_path)
    binds = _populate_calls(monkeypatch)
    _press(Qt.Key.Key_Right)  # ring on item 3, picture still item 2
    assert overlay._current_idx == 2

    _press(Qt.Key.Key_Return)
    _wait_for_click(qtbot)
    assert overlay._current_idx == 3, "Enter must show the focused item"
    assert overlay._current_item.path == items[3].path
    assert binds == [True], f"exactly one re-bind, view preserved: {binds}"

    focused = _press(Qt.Key.Key_Left)
    assert overlay._current_idx == 3
    assert nav.thumb_for_path(overlay, str(items[2].path)) is focused, (
        "the ring must survive the rebuild Enter triggers, or arrows die"
    )

    # The analysis pass re-stamps ranks → the strip's fingerprint mismatches and
    # the thumbs are REPLACED (the churn that killed navigation live): the ring
    # has to come back on the same item, or the next arrow is dead.
    _churn_strip(overlay, items)
    focused = QApplication.focusWidget()
    assert focused is nav.thumb_for_path(overlay, str(items[2].path)), (
        f"the ring must be re-asserted on the rebuilt thumb: {_name(focused)}"
    )
    assert _press(Qt.Key.Key_Left) is nav.thumb_for_path(overlay, str(items[1].path))
    assert _press(Qt.Key.Key_Right) is nav.thumb_for_path(overlay, str(items[2].path))
    assert overlay._current_idx == 3, "the arrows never re-bind after Enter"
    assert binds == [True], "no second re-bind from the arrows after Enter"
    overlay.hide()


def test_action_row_three_buttons_are_reachable_and_enter_presses_one(
    qtbot, tmp_path, monkeypatch
) -> None:
    """Report (c): ↓ reaches the row, ←/→ pick among THREE buttons, Enter presses."""
    overlay, _items = _open(qtbot, tmp_path)
    binds = _populate_calls(monkeypatch)
    pressed: list[str] = []
    for button, name in (
        (overlay._set_source_btn, "source"),
        (overlay._reject_btn, "reject"),
        (overlay._delete_btn, "delete"),
    ):
        button.clicked.connect(lambda _checked=False, n=name: pressed.append(n))

    focused = _press(Qt.Key.Key_Down)
    assert overlay._action_bar.isAncestorOf(focused), f"↓ must enter the row: {_name(focused)}"
    # ↓ lands on the button nearest the thumb (the toolkit's 2D rule); walk
    # both ways to prove all three are reachable, then settle on the last one.
    reached = [_name(focused)]
    for key in (Qt.Key.Key_Left, Qt.Key.Key_Left):
        reached.append(_name(_press(key)))
    for key in (Qt.Key.Key_Right, Qt.Key.Key_Right, Qt.Key.Key_Right):
        reached.append(_name(_press(key)))
    assert set(reached) == {
        "quicklook_set_source",
        "quicklook_reject",
        "quicklook_delete",
    }, f"←/→ must reach every action button: {reached}"
    assert overlay._action_bar.isAncestorOf(QApplication.focusWidget())
    assert _name(QApplication.focusWidget()) == "quicklook_delete", "clamped at the edge"

    # Walk back onto Reject and press it: Enter must press THAT button and must
    # not confirm the strip (the Reject handler rebuilds the strip only).
    _press(Qt.Key.Key_Left)
    assert _name(QApplication.focusWidget()) == "quicklook_reject"
    _press(Qt.Key.Key_Return)
    _wait_for_click(qtbot)
    assert pressed == ["reject"], f"Enter presses the focused button: {pressed}"
    assert binds == [], "the strip must not be confirmed from the action row"

    # ↑ returns to the strip, with the ring back on a thumb.
    focused = _press(Qt.Key.Key_Up)
    assert nav.strip_thumbs(overlay)[0].parentWidget() is not None
    assert overlay._strip_row.isAncestorOf(focused), _name(focused)
    overlay.hide()


def test_cursor_is_the_thumb_button_not_its_container(qtbot, tmp_path) -> None:
    """Report (d): the ring lands on ``quicklook_strip_N``, never a wrapper.

    A container is a plain ``QWidget`` — focusing one paints no indication (the
    live "no indication while navigating" report). The row therefore has to
    resolve to the thumb Buttons only, which also means the strip's
    ``OverlayScrollArea`` (StrongFocus by default) and the rank pills (real
    Buttons) must not be cursor targets. Falsified by: dropping either
    ``setFocusPolicy(NoFocus)`` (build.py / rebuild.py) — the row then reports
    5+ targets and an arrow parks the ring on an indicator that never moves.
    """
    overlay, _items = _open(qtbot, tmp_path)
    focused = _press(Qt.Key.Key_Right)
    assert focused is not None and focused.objectName().startswith("quicklook_strip_")
    assert isinstance(focused, Button)
    for container in list(overlay._strip_buttons):
        assert container.focusPolicy() == Qt.FocusPolicy.NoFocus
        assert focused is not container, "the container paints no ring"

    row_section = nav.section_of(overlay)
    targets = row_section._focusable(overlay._strip_row)
    assert [w.objectName() for w in targets] == [
        f"quicklook_strip_{i}" for i in range(len(targets))
    ], "the strip row's targets are its thumbs and nothing else"
    assert len(targets) == len(overlay._series_items)
    bar_targets = row_section._focusable(overlay._action_bar)
    assert [w.objectName() for w in bar_targets] == [
        "quicklook_set_source",
        "quicklook_reject",
        "quicklook_delete",
    ], "the action row's targets are exactly its three buttons"
    overlay.hide()


def test_the_cursor_is_the_focus_ring_not_a_painted_marker(qtbot, tmp_path) -> None:
    """One cursor vocabulary: no cursor-marker property, no cursor painter.

    Falsified by: restoring strip/paint.py's cursor-outline painter and
    nav_section's marker writer (both deleted in this change) — the thumbs then
    carry that property again and the marker is a second, panel-local cursor.
    """
    from tabs.image_gallery.ui.quick_look.strip import paint

    assert not hasattr(paint, "_strip_cursor_outline"), (
        "the painted cursor marker belongs to the focus ring now"
    )
    overlay, _items = _open(qtbot, tmp_path)
    _press(Qt.Key.Key_Right)
    for thumb in nav.strip_thumbs(overlay):
        assert thumb.property("strip_cursor") is None, (
            "the thumb must carry no cursor property — the ring is the cursor"
        )
    overlay.hide()


def test_move_strip_focus_is_the_circle_handler(qtbot, tmp_path) -> None:
    """The ‹/› circles step the same ring (focus movement, not a re-bind)."""
    overlay, items = _open(qtbot, tmp_path)
    assert nav.move_strip_focus(overlay, 1) is True
    assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[3].path))
    assert overlay._current_idx == 2, "a circle press must not re-bind the picture"
    assert nav.move_strip_focus(overlay, -1) is True
    assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[2].path))

    # From the action row the circles put the ring back on the shown item.
    # From the action row the circles put the ring back on the strip first (the
    # item on screen) and then step from there — the ring, never the picture.
    _press(Qt.Key.Key_Down)
    assert overlay._action_bar.isAncestorOf(QApplication.focusWidget())
    assert nav.move_strip_focus(overlay, 1) is True
    assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[3].path))
    assert overlay._current_idx == 2, "a circle press must never re-bind the picture"
    overlay.hide()


def test_a_background_rebuild_keeps_the_ring_in_the_panel(qtbot, tmp_path) -> None:
    """Report (e): a repopulate behind the user's back must not move focus out.

    The analysis pass re-stamps ranks, which mismatches the strip's fingerprint
    and takes the FULL rebuild path — the one that deletes every thumb widget.
    The snapshot by ``gallery_path`` has to put the ring back on the live thumb,
    so the panel keeps the keyboard (and a repopulate must never steal focus
    from a row button).

    Falsified by: dropping ``snapshot_focus`` at the top of ``rebuild_strip`` or
    ``restore_strip_focus`` at its sync point — the ring is then left on a
    deleted widget (focus escapes the panel or lands on nothing).
    """
    overlay, items = _open(qtbot, tmp_path)
    _press(Qt.Key.Key_Right)  # ring on the LAST thumb (item 3), picture item 2
    focused = QApplication.focusWidget()
    assert focused is nav.thumb_for_path(overlay, str(items[3].path))

    _churn_strip(overlay, items)
    focused = QApplication.focusWidget()
    assert focused is nav.thumb_for_path(overlay, str(items[3].path)), (
        f"the rebuilt strip must keep the ring on the same item: {_name(focused)}"
    )
    assert overlay.isAncestorOf(focused), "focus must stay inside the panel"

    # ...and a rebuild while the user is on a row button must not steal it.
    _press(Qt.Key.Key_Down)
    button = QApplication.focusWidget()
    assert overlay._action_bar.isAncestorOf(button)
    _churn_strip(overlay, items)
    assert QApplication.focusWidget() is button, "the repopulate stole focus"
    overlay.hide()


def test_a_rebuild_never_steals_the_key_pressed_right_after_it(qtbot, tmp_path) -> None:
    """A programmatic driver can inject the next arrow in the SAME tick.

    The rebuild's restore is deferred one tick (a rebuild can replace the thumb
    widgets again after the sync call). That late attempt must only ever fill a
    LOST ring — with the guard removed it pulls the ring back off the thumb the
    key had just reached (measured while writing these tests; the app's control
    channel re-anchors and injects keys back-to-back, so the window is real).
    Falsified by: dropping ``only_if_lost`` from the deferred ``_place_cursor``.
    """
    overlay, items = _open(qtbot, tmp_path)
    _press(Qt.Key.Key_Right)  # ring on item 3
    before = QApplication.focusWidget()
    assert before is nav.thumb_for_path(overlay, str(items[3].path))

    items[-1].rank = int(getattr(items[-1], "rank", 1) or 1) + 7
    from tabs.image_gallery.services.rank_badge import stamp_badges

    stamp_badges(items)
    overlay._rebuild_strip()  # schedules the deferred re-apply
    focused = _press(Qt.Key.Key_Left)  # ... which must not override this
    assert focused is nav.thumb_for_path(overlay, str(items[2].path)), (
        f"the late re-apply stole the key: {_name(focused)}"
    )
    assert overlay._current_idx == 2, "arrows never re-bind"
    overlay.hide()


def test_up_and_down_wrap_inside_the_panel(qtbot, tmp_path) -> None:
    """Arrows while the panel is open must not reach the gallery grid behind.

    ``ToolbarRowsSection`` yields ``↓``/``↑`` past its last/first row so the
    shell can hand focus to a neighbouring section — correct for a toolbar, wrong
    for a modal panel: with a section registered either side, the yield walks the
    ring onto a card behind the veil while the panel stays up with no ring on it
    (measured 2026-10-17). The panel wraps instead: ``↑`` from the strip lands on
    the action row, ``↓`` from the action row lands back on the item on screen.
    Falsified by: removing the wrap from ``QuickLookNavSection.navigate`` — Up on
    the first thumb then focuses the neighbour registered before the panel.
    """
    items = _series(tmp_path, 4)
    overlay = _make_overlay(qtbot)
    parent = overlay.parentWidget()
    parent.resize(1280, 800)
    parent.show()
    QApplication.processEvents()
    above = QWidget(parent)
    above.setObjectName("stand-in-above")
    above.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    below = QWidget(parent)
    below.setObjectName("stand-in-below")
    below.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    manager = NavigationManager.get_instance()
    manager.register(above, _NeighbourSection(above))  # registered BEFORE the panel
    try:
        _show(overlay, items[2], items)
        manager.register(below, _NeighbourSection(below))  # ... and one AFTER it
        QApplication.processEvents()
        assert overlay.isVisible() and QApplication.focusWidget() is not None
        assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[2].path))

        focused = _press(Qt.Key.Key_Up)  # first row, at the panel's top edge
        assert focused is not above, "Up must not hand focus to the page behind"
        assert overlay.isAncestorOf(focused), _name(focused)
        assert overlay._action_bar.isAncestorOf(focused), (
            f"the top edge wraps to the bottom row: {_name(focused)}"
        )

        focused = _press(Qt.Key.Key_Down)  # bottom edge wraps back to the strip
        assert QApplication.focusWidget() is not below, (
            "Down must not hand focus to the page below the panel"
        )
        assert nav.thumb_for_path(overlay, str(items[2].path)) is focused, (
            f"the bottom edge wraps to the item on screen: {_name(focused)}"
        )
        assert overlay._current_idx == 2, "wrapping is movement, not a re-bind"
    finally:
        manager.unregister(overlay)
        manager.unregister(above)
        manager.unregister(below)
        overlay.hide()


def test_reopening_puts_the_ring_back_on_the_shown_item(qtbot, tmp_path) -> None:
    """Reopen: the ring is on the shown item, not on the first thumb.

    The panel is registered LAST in ``show_for`` (after ``show_overlay()``'s own
    focus grab) and the section's ``focus_first`` lands on the shown item, so
    the manager's deferred owner-bootstrap can never light the ring on thumb 0
    (found while writing these tests: with the registration before
    ``show_overlay`` the reopen ring sat on the first thumb).
    Falsified by: reverting either half (register-first ordering, or
    ``focus_first`` delegating straight to the toolkit row).
    """
    overlay, items = _open(qtbot, tmp_path)  # ring on item 2, picture item 2
    _press(Qt.Key.Key_Right)  # ring on item 3, picture unchanged
    overlay.hide()
    QApplication.processEvents()

    _show(overlay, items[2], items)
    QApplication.processEvents()
    focused = QApplication.focusWidget()
    assert focused is nav.thumb_for_path(overlay, str(items[2].path)), (
        f"a reopen must anchor on the item it was opened for: {_name(focused)}"
    )
    overlay.hide()


def test_closing_the_panel_leaves_the_navigation_graph(qtbot, tmp_path) -> None:
    """The panel's close path drops the section (and restores the opener).

    The focus restore itself is pinned by ``test_quick_look_focus_restore.py``;
    what this adds is that no section outlives the panel — a stale section would
    keep claiming arrows for a hidden overlay.
    """
    overlay, _items = _open(qtbot, tmp_path)
    manager = NavigationManager.get_instance()
    assert any(owner is overlay for owner, _spec in manager._sections)
    overlay.hide()
    QApplication.processEvents()
    assert nav.section_of(overlay) is None
    assert not any(owner is overlay for owner, _spec in manager._sections)
    assert nav.move_strip_focus(overlay, 1) is False, "a closed panel navigates nothing"
