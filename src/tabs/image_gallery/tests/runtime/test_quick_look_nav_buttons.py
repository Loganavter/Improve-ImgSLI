"""Quick Look's declared rows own every control — no click-only or dead stops.

Audit ``inv-nav-coverage-audit-2026-10-19`` rank 4: the panel declared two rows
(``_strip_row`` + ``_action_bar``) while the ✕ close button sat in the title
layout *outside* every row, the ``‹``/``›`` circles and the SOURCE inset thumb
were parented to the overlay with no row at all, and the inset thumb was a
``StrongFocus`` ``Button`` with no action — a Tab stop that did nothing on
Enter.

The contract this file pins, over the real ``QuickLookOverlay`` and the real
``NavigationManager`` (offscreen; keys through ``QApplication.sendEvent`` so the
whole manager → section → widget path runs):

* the panel declares **three** rows in visual order — the ✕ close button (the
  panel's header row, same single-control-row idiom as Clean Review's header),
  the filmstrip and the action bar — and every ``StrongFocus`` control inside
  the overlay belongs to one of them;
* ``↓``/``↑`` walk those rows and wrap inside the veil, so the ✕ is reachable
  from the strip and ``Enter``/``Space`` dismiss the panel (the toolkit
  ``Button`` activates itself — the section never claims Return/Space);
* closing restores the opener's focus and unregisters the section;
* ``‹``/``›`` and the SOURCE inset are explicitly **NoFocus** click-only
  affordances: Left/Right already walk the preview cursor ring, so a second
  focus stop for the same movement would be inert duplication, and the inset is
  an informational caption with no action at all.

Every test carries a ``Falsified by:`` note naming the code whose removal turns
it red. All of them fail on the pre-audit tree (see ``DONE.md``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection

from tabs.image_gallery.models import GalleryItem, Mode
from tabs.image_gallery.tests.test_quicklook_strip import (
    _make_overlay,
    _real_png,
    _show,
)
from tabs.image_gallery.ui.quick_look import nav_section as nav


@pytest.fixture(autouse=True)
def _restore_nav_modality():
    """Undo the app-wide input-modality flip every injected key causes."""
    manager = NavigationManager.get_instance()
    previous = getattr(manager, "_last_input_keyboard", False)
    yield
    manager._last_input_keyboard = previous


def _series(tmp_path, n: int = 4) -> list[GalleryItem]:
    paths = [_real_png(tmp_path, f"b{i}.png") for i in range(n)]
    return [GalleryItem(path=p, mtime_ns=i + 1, rank=i + 1) for i, p in enumerate(paths)]


def _open(qtbot, tmp_path, n: int = 4, current: int = 2):
    """A shown panel with *n* items; the ring opens on the shown item."""
    items = _series(tmp_path, n)
    overlay = _make_overlay(qtbot)
    parent = overlay.parentWidget()
    parent.resize(1280, 800)
    parent.show()
    QApplication.processEvents()
    _show(overlay, items[current], items)
    QApplication.processEvents()
    return overlay, items


def _press(key: Qt.Key, modifiers=Qt.KeyboardModifier.NoModifier) -> QWidget | None:
    """Deliver a real key press to the focused widget (manager path included)."""
    focused = QApplication.focusWidget()
    assert focused is not None, "nothing is focused — the test cannot drive the panel"
    QApplication.sendEvent(focused, QKeyEvent(QEvent.Type.KeyPress, key, modifiers))
    QApplication.processEvents()
    return QApplication.focusWidget()


def _name(widget) -> str:
    return str(widget.objectName()) if widget is not None else "<none>"


def _in_row(row, widget) -> bool:
    try:
        return bool(
            row is not None
            and widget is not None
            and (row is widget or row.isAncestorOf(widget))
        )
    except Exception:
        return False


def _inside(overlay, widget) -> bool:
    return widget is not None and (widget is overlay or overlay.isAncestorOf(widget))


class _NeighbourSection:
    """A stand-in page section behind the veil (registered before the panel)."""

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


def test_three_rows_in_visual_order_and_every_control_owned(qtbot, tmp_path) -> None:
    """The ✕ is the panel's header row; all three rows are real, owned widgets.

    Falsified by: leaving the close button in the title layout with ``rows()``
    returning only ``[strip, action bar]`` — the ✕ is then owned by no row and
    arrow/Tab navigation can never make it a proper cursor target.
    """
    overlay, _items = _open(qtbot, tmp_path)
    section = nav.section_of(overlay)
    assert section is not None
    assert isinstance(section, ToolbarRowsSection), "rows must be the toolkit section"
    assert section.modal is True

    rows = nav.rows(overlay)
    assert rows == [overlay._close_btn, overlay._strip_row, overlay._action_bar], (
        f"rows must be [close, strip, action bar] top-to-bottom: {[_name(r) for r in rows]}"
    )
    assert all(row is not None and row.isVisible() for row in rows)
    # Visual order is what the toolkit sorts by (all three share a parent).
    assert [type(r).__name__ for r in section._rows()] == [
        type(r).__name__ for r in rows
    ]

    assert section.owns(overlay._close_btn) is True
    assert section._focusable(overlay._close_btn) == [overlay._close_btn], (
        "a single-control row counts the row widget itself as its target"
    )
    assert overlay._close_btn.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert section.owns(overlay._strip_row)
    assert section.owns(overlay._action_bar)
    overlay.hide()


def test_no_strong_focus_widget_lives_outside_the_declared_rows(qtbot, tmp_path) -> None:
    """The "every stop is actionable" rule, mechanically: no unowned focus stop.

    Before the audit the panel had four: the ✕, the ``‹``/``›`` circles and the
    inert SOURCE inset thumb were StrongFocus but lived in no row (and the
    sidebar scroller inherited StrongFocus too, the same defect the strip
    scroller already documents).

    Falsified by: re-adding ``StrongFocus`` to any of ``_prev_btn``,
    ``_next_btn``, ``_source_inset_pix`` or the sidebar scroller
    ``right_scroll`` (built in ``overlay_build/build.py``, objectName
    quicklook_right_scroll), or by dropping the ✕ from ``nav.rows`` — the walk
    below then finds a focusable widget that no row owns.
    """
    overlay, _items = _open(qtbot, tmp_path, current=2)
    rows = nav.rows(overlay)
    assert len(rows) == 3

    unowned: list[str] = []
    for widget in overlay.findChildren(QWidget):
        try:
            if (
                widget.focusPolicy() == Qt.FocusPolicy.StrongFocus
                and widget.isVisible()
                and widget.isEnabled()
                and not any(_in_row(row, widget) for row in rows)
                and widget is not overlay
            ):
                unowned.append(f"{type(widget).__name__}:{widget.objectName()}")
        except Exception:
            continue
    assert unowned == [], f"StrongFocus widgets outside every declared row: {unowned}"

    # The three resolved affordances, explicitly.
    assert overlay._prev_btn.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert overlay._next_btn.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert overlay._source_inset_pix.focusPolicy() == Qt.FocusPolicy.NoFocus
    overlay.hide()


def test_down_up_walk_header_strip_actions_and_wrap_inside_the_veil(qtbot, tmp_path) -> None:
    """↓/↑ visit close → strip → action bar and wrap without leaving the veil.

    A stand-in page widget + section are registered *before* the panel, so a
    boundary that yielded to a neighbour would really move focus out of the
    veil (the shape ``test_quicklook_modal_nav.py`` uses).

    Falsified by: dropping the third (header) row, or removing the wrap from
    ``QuickLookNavSection.navigate`` — Up on the strip then stops at the strip
    (or yields to the page) and the ✕ is unreachable from the keyboard.
    """
    overlay, _items = _open(qtbot, tmp_path)
    parent = overlay.parentWidget()
    page = QWidget(parent)
    page.setObjectName("stand-in-page-behind")
    page.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    manager = NavigationManager.get_instance()
    manager.register(page, _NeighbourSection(page))
    try:
        assert _inside(overlay, QApplication.focusWidget())
        assert _in_row(overlay._strip_row, QApplication.focusWidget())

        focused = _press(Qt.Key.Key_Down)  # strip -> action bar
        assert _in_row(overlay._action_bar, focused), _name(focused)

        focused = _press(Qt.Key.Key_Down)  # bottom edge -> wraps to the header
        assert focused is overlay._close_btn, (
            f"the bottom edge must wrap to the top row (✕): {_name(focused)}"
        )

        focused = _press(Qt.Key.Key_Down)  # header -> strip
        assert _in_row(overlay._strip_row, focused), _name(focused)

        focused = _press(Qt.Key.Key_Up)  # strip -> header
        assert focused is overlay._close_btn, (
            f"Up from the strip must reach the ✕: {_name(focused)}"
        )

        focused = _press(Qt.Key.Key_Up)  # top edge -> wraps to the action bar
        assert _in_row(overlay._action_bar, focused), _name(focused)

        # Keep pressing both edges: nothing ever reaches the page behind.
        for key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Down):
            focused = _press(key)
            assert _inside(overlay, focused), f"an arrow escaped the veil: {_name(focused)}"
        assert page.hasFocus() is False
        assert manager is not None
    finally:
        manager.unregister(page)
        overlay.hide()


def test_enter_on_the_close_button_dismisses_and_restores_the_opener(qtbot) -> None:
    """The ✕ is reachable by arrows and Enter/Space really dismiss the panel.

    Uses the real ``ImageGalleryWidget`` so the close path is the production one:
    ``dismiss`` → ``hide`` → ``unregister`` → focus back to the opening card.

    Falsified by: a section that claims Return/Space (the toolkit Button never
    activates), a ✕ that is not a row (arrows cannot reach it), or a close path
    that leaves the section registered / the ring on the floor.
    """
    from tabs.image_gallery.widget import ImageGalleryWidget

    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    qtbot.waitExposed(w)
    items = [
        GalleryItem(path=Path(f"/gallery/close.{i}.png"), mtime_ns=i + 1)
        for i in range(3)
    ]
    w.rebuild_grid(items)
    QTest.qWait(20)
    # Storeless widget: the production controller supplies this state mirror.
    # A multi-item series is what makes the filmstrip a real row (a single-item
    # series legitimately hides the strip row), so the arrow path below walks
    # all three rows.
    w.state = SimpleNamespace(
        mode=Mode.FIDELITY, source_path=None, series=[list(items)], items=items
    )
    card = w._grid_view.card_for(items[1].path)
    assert card is not None
    assert w._grid_view.focus_card(card) is True
    QTest.qWait(20)

    w.show_quick_look(items[1])
    overlay = w._quick_look_overlay
    QTest.qWait(20)
    assert overlay.isVisible()
    assert nav.section_of(overlay) is not None
    assert _in_row(overlay._strip_row, QApplication.focusWidget())

    focused = _press(Qt.Key.Key_Up)  # strip -> header row
    assert focused is overlay._close_btn, (
        f"the close button must be an arrow target: {_name(focused)}"
    )

    _press(Qt.Key.Key_Return)
    QTest.qWait(20)
    assert not overlay.isVisible(), "Enter on ✕ must dismiss Quick Look"
    assert nav.section_of(overlay) is None, "the close path must unregister"
    assert not any(owner is overlay for owner, _spec in NavigationManager.get_instance()._sections)
    assert QApplication.focusWidget() is card, (
        f"focus must return to the opener card, got {_name(QApplication.focusWidget())}"
    )


def test_space_also_activates_the_close_button(qtbot, tmp_path) -> None:
    """Space is the Button's second activation key — the section never claims it.

    Falsified by: adding ``Return``/``Enter``/``Space`` to ``extra_keys`` (the
    manager would then route activation to the section instead of the Button).
    """
    overlay, _items = _open(qtbot, tmp_path)
    section = nav.section_of(overlay)
    raw = getattr(section, "extra_keys", frozenset())
    assert Qt.Key.Key_Return not in raw
    assert Qt.Key.Key_Enter not in raw
    assert Qt.Key.Key_Space not in raw

    overlay._close_btn.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    assert QApplication.focusWidget() is overlay._close_btn
    _press(Qt.Key.Key_Space)
    QTest.qWait(20)
    assert not overlay.isVisible(), "Space on ✕ must dismiss Quick Look"


def test_prev_next_stay_click_only_cursor_steps(qtbot, tmp_path) -> None:
    """``‹``/``›`` are NoFocus but still step the preview's focus ring on click.

    Left/Right already move the ring (``nav_section.move_strip_focus``), so the
    circles are a mouse duplicate of that movement, not a second cursor — the
    written decision is "NoFocus, the arrows own the movement".

    Falsified by: dropping the NoFocus decision (they become unowned Tab stops)
    or by removing the ``clicked`` hookup while making them NoFocus (a dead
    button).
    """
    overlay, items = _open(qtbot, tmp_path, current=2)
    assert overlay._prev_btn.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert overlay._next_btn.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert overlay._prev_btn.isEnabled() and overlay._next_btn.isEnabled()
    assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[2].path))

    overlay._next_btn.clicked.emit()
    QApplication.processEvents()
    assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[3].path))
    assert overlay._current_idx == 2, "a circle press moves the ring, never the picture"

    overlay._prev_btn.clicked.emit()
    QApplication.processEvents()
    assert QApplication.focusWidget() is nav.thumb_for_path(overlay, str(items[2].path))
    assert overlay._current_idx == 2
    overlay.hide()


def test_tab_never_lands_on_the_source_inset_or_a_circle(qtbot, tmp_path) -> None:
    """The SOURCE inset is informational: Tab must pass it by.

    The inset is a card-style ``Button`` that only paints a caption/tooltip; it
    has no action, so the written decision is "NoFocus — informational only".

    Falsified by: leaving the inset thumb ``StrongFocus`` — the Tab ring then
    parks on a control where Enter does nothing (the reported dead stop).
    """
    overlay, _items = _open(qtbot, tmp_path)
    assert overlay._source_inset_pix.focusPolicy() == Qt.FocusPolicy.NoFocus

    seen: list[str] = []
    for _ in range(16):
        focused = _press(Qt.Key.Key_Tab)
        assert _inside(overlay, focused), f"Tab escaped the veil: {_name(focused)}"
        seen.append(_name(focused))
        assert focused is not overlay._source_inset_pix, "Tab reached the inert inset"
        assert focused not in (overlay._prev_btn, overlay._next_btn)
    overlay.hide()
