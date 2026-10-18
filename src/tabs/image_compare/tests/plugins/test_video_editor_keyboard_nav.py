"""Video editor dialog keyboard navigation — one modal section over the rows.

Pins, over the real ``VideoEditorDialog`` offscreen:

* the dialog registers its nav section on show and drops it on close
  (idempotent across re-shows);
* ``↑``/``↓`` walk the rows in visual order — timeline → toolbar → export →
  tabs → preview quality → fps → resolution — and ``←``/→ move within a row;
* an arrow at the edge is consumed: focus never escapes to a section
  registered behind the dialog (the workspace tab's section in production).
  A non-modal twin of the same section is the control — it *does* attempt the
  hand-off, so the edge test is not vacuously green;
* the pre-existing Space semantics are unchanged by the markup: the timeline
  keeps its own Space handling (the dialog shortcut's guard stays silent), a
  line edit still types a space, and a non-consuming focused widget still
  toggles playback through the dialog-level shortcut.

Runs offscreen: the real dialog + the real NavigationManager, keys delivered
through ``QApplication.sendEvent`` to the focused widget, so the whole
manager → section → widget path is exercised.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.managers import NavigationManager
from sli_ui_toolkit.ui.managers import nav_graph

from tabs.image_compare.plugins.video_editor.dialog.nav import VideoEditorNavSection
from tabs.image_compare.plugins.video_editor.dialog.shell import VideoEditorDialog

# The dialog's nav rows in visual top→bottom order (dialog/nav.py).
_ROW_NAMES = (
    "res_row",
    "fps_row",
    "preview_row",
    "tabs",
    "export_row",
    "toolbar_frame",
    "scroll_area",
)


class _FakePresenter:
    main_controller = None


class _FakeExportController:
    store = None
    presenter = _FakePresenter()


@pytest.fixture(autouse=True)
def _restore_nav_modality():
    """Undo the app-wide input-modality flip every injected key causes.

    ``NavigationManager.eventFilter`` sets ``_last_input_keyboard`` on each
    KeyPress, which decides whether a later programmatic focus grant paints
    the keyboard ring; without this, every later test inherits "keyboard mode".
    """
    manager = NavigationManager.get_instance()
    previous = getattr(manager, "_last_input_keyboard", False)
    yield
    manager._last_input_keyboard = previous


def _destroy_dialog(dlg) -> None:
    """Close *dlg* and let its ``WA_DeleteOnClose`` deletion land.

    The teardown workhorse for every dialog in this file — deliberately NOT
    ``qtbot.addWidget``-registered: pytest-qt's teardown auto-closes every
    registered widget, and a second ``close()`` on a dialog a test already
    closed raises ``RuntimeError: Internal C++ object already deleted``
    (WA_DeleteOnClose deletes during the test's own ``processEvents()``).
    Owning the lifetime here keeps exactly one close per dialog, so no
    widget is ever touched after its C++ object is gone.
    """
    try:
        if dlg.isVisible():
            dlg.close()
        QApplication.processEvents()  # deliver the DeferredDelete
    except RuntimeError:
        # Already deleted by the test's own close() — nothing left to do.
        pass
    QApplication.processEvents()


@pytest.fixture
def dialog(qtbot):
    dlg = VideoEditorDialog([], _FakeExportController(), None)
    dlg.show()
    qtbot.waitExposed(dlg)
    yield dlg
    _destroy_dialog(dlg)


def _press(key: Qt.Key) -> QWidget | None:
    """Deliver a real key press to the focused widget (manager path included).

    Uses ``QTest.keyClick`` — the realistic delivery path: Qt runs the
    ShortcutOverride claim phase before the KeyPress, exactly as a real key
    press does (``QApplication.sendEvent`` skips it, which changes line-edit
    and shortcut semantics).
    """
    focused = QApplication.focusWidget()
    assert focused is not None, "nothing is focused — the test cannot drive the dialog"
    QTest.keyClick(focused, key)
    QApplication.processEvents()
    return QApplication.focusWidget()


def _row_of(dialog, widget) -> str | None:
    """The nav row containing *widget* (or None when focus is outside the rows)."""
    for name in _ROW_NAMES:
        row = getattr(dialog, name)
        if widget is row or row.isAncestorOf(widget):
            return name
    return None


def _focus_reason() -> Qt.FocusReason:
    """Modality-aware focus reason — never a literal (guide: no OtherFocusReason)."""
    return NavigationManager.get_instance().current_focus_reason()


def _shown_dialog(qtbot) -> VideoEditorDialog:
    # Not qtbot.addWidget — see _destroy_dialog: the tests below close the
    # dialog themselves, and pytest-qt's auto-close would double-close it.
    dlg = VideoEditorDialog([], _FakeExportController(), None)
    dlg.show()
    qtbot.waitExposed(dlg)
    return dlg


class _BehindSection:
    """Stands in for the workspace tab's section registered behind the dialog.

    Records every focus grant and accepts it by focusing an anchor widget —
    so a hand-off attempt is observable even though the behind window is not
    the active one.
    """

    def __init__(self, window: QWidget, anchor: QWidget) -> None:
        self._window = window
        self.anchor = anchor
        self.grants: list[str] = []

    def owns(self, widget) -> bool:
        return widget is self._window or self._window.isAncestorOf(widget)

    def navigate(self, key: int, widget) -> bool:
        return False

    def focus_first(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        self.grants.append("first")
        self.anchor.setFocus(reason)
        return True

    def focus_last(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        self.grants.append("last")
        self.anchor.setFocus(reason)
        return True

    @property
    def extra_keys(self) -> frozenset[int]:
        return frozenset()


class _NonModalSection(VideoEditorNavSection):
    """The production section with the modal flag off — the escape control."""

    @property
    def modal(self) -> bool:
        return False


def _show_behind(qtbot):
    """A visible window with a section registered — the 'tab behind the dialog'."""
    behind = QWidget()
    qtbot.addWidget(behind)
    behind.resize(800, 600)
    behind.show()
    anchor = QWidget(behind)
    # StrongFocus: a plain QWidget defaults to NoFocus, and setFocus() on a
    # NoFocus widget is a no-op — the hand-off grant would be recorded but
    # app focus would never actually move (the escape would be unobservable).
    anchor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    anchor.resize(100, 50)
    anchor.show()
    section = _BehindSection(behind, anchor)
    NavigationManager.get_instance().register(behind, section)
    return behind, section


# ------------------------------------------------------------------
# Registration lifecycle
# ------------------------------------------------------------------


def test_section_registered_on_show(dialog):
    graph = nav_graph.snapshot()
    assert any(
        node.owner == "VideoEditorDialog" and node.section == "VideoEditorNavSection"
        for node in graph.nodes
    ), f"dialog section missing from the nav graph: {graph.nodes}"


def test_section_unregistered_on_close(dialog):
    dialog.close()
    QApplication.processEvents()
    graph = nav_graph.snapshot()
    assert not any(node.owner == "VideoEditorDialog" for node in graph.nodes)


def test_registration_idempotent_on_reshow(dialog):
    dialog.hide()
    QApplication.processEvents()
    dialog.show()
    QApplication.processEvents()
    graph = nav_graph.snapshot()
    owners = [node.owner for node in graph.nodes]
    assert owners.count("VideoEditorDialog") == 1


# ------------------------------------------------------------------
# Row traversal
# ------------------------------------------------------------------


def test_focus_entry_is_timeline_on_show(dialog):
    """The existing showEvent entry (timeline first) is preserved."""
    assert QApplication.focusWidget() is dialog.timeline


def test_up_walks_rows_in_visual_order(dialog):
    """From the timeline entry, Up crosses the rows bottom→top; the last
    press is the modal edge — consumed, focus stays on the first row."""
    assert QApplication.focusWidget() is dialog.timeline
    seen = []
    for _ in range(len(_ROW_NAMES)):
        _press(Qt.Key.Key_Up)
        seen.append(_row_of(dialog, QApplication.focusWidget()))
    assert seen == [
        "toolbar_frame",
        "export_row",
        "tabs",
        "preview_row",
        "fps_row",
        "res_row",
        "res_row",
    ]


def test_down_walks_rows_in_visual_order(dialog):
    """From the first row, Down crosses the rows top→bottom; the last press
    is the modal edge — consumed, focus stays on the timeline."""
    dialog.edit_width.setFocus(_focus_reason())
    QApplication.processEvents()
    seen = []
    for _ in range(len(_ROW_NAMES)):
        _press(Qt.Key.Key_Down)
        seen.append(_row_of(dialog, QApplication.focusWidget()))
    assert seen == [
        "fps_row",
        "preview_row",
        "tabs",
        "export_row",
        "toolbar_frame",
        "scroll_area",
        "scroll_area",
    ]


def test_left_right_move_within_toolbar_row(dialog):
    """←/→ step through the toolbar's buttons in screen-x order and are
    consumed at the row edges (no wrap, no hand-off)."""
    toolbar = (dialog.btn_play, dialog.btn_undo, dialog.btn_redo, dialog.btn_trim)
    dialog.btn_play.setFocus(_focus_reason())
    QApplication.processEvents()

    seq = []
    for _ in range(3):
        _press(Qt.Key.Key_Right)
        focused = QApplication.focusWidget()
        seq.append(toolbar.index(focused) if focused in toolbar else None)
    assert seq == [1, 2, 3]  # undo → redo → trim
    _press(Qt.Key.Key_Right)
    assert QApplication.focusWidget() is dialog.btn_trim  # right edge: consumed

    seq = []
    for _ in range(3):
        _press(Qt.Key.Key_Left)
        focused = QApplication.focusWidget()
        seq.append(toolbar.index(focused) if focused in toolbar else None)
    assert seq == [2, 1, 0]  # redo → undo → play
    _press(Qt.Key.Key_Left)
    assert QApplication.focusWidget() is dialog.btn_play  # left edge: consumed


# ------------------------------------------------------------------
# Modal edge confinement
# ------------------------------------------------------------------


def test_modal_edge_arrows_stay_inside_dialog(qtbot):
    """With the dialog's modal section registered, an arrow at the edge is
    consumed: the section behind never receives a focus grant and focus stays
    inside the dialog."""
    manager = NavigationManager.get_instance()
    behind, behind_section = _show_behind(qtbot)
    try:
        dialog = _shown_dialog(qtbot)
        try:
            dialog.raise_()
            dialog.activateWindow()
            QApplication.processEvents()

            # Up from the first row: consumed at the top edge.
            dialog.edit_width.setFocus(_focus_reason())
            QApplication.processEvents()
            _press(Qt.Key.Key_Up)
            assert behind_section.grants == []
            assert _row_of(dialog, QApplication.focusWidget()) == "res_row"

            # Down from the timeline (last row): consumed at the bottom edge.
            dialog.timeline.setFocus(_focus_reason())
            QApplication.processEvents()
            _press(Qt.Key.Key_Down)
            assert behind_section.grants == []
            assert _row_of(dialog, QApplication.focusWidget()) == "scroll_area"
        finally:
            if dialog.isVisible():
                dialog.close()
            QApplication.processEvents()
    finally:
        manager.unregister(behind)


def test_nonmodal_twin_would_escape(qtbot):
    """Control for the edge test: the same section with ``modal`` off *does*
    hand focus to the section registered behind — so the modal-edge test above
    can actually detect an escape (it is not vacuously green)."""
    manager = NavigationManager.get_instance()
    behind, behind_section = _show_behind(qtbot)
    try:
        dialog = _shown_dialog(qtbot)
        try:
            # Swap the production modal section for a non-modal twin.
            manager.unregister(dialog)
            manager.register(dialog, _NonModalSection(dialog))
            dialog.raise_()
            dialog.activateWindow()
            QApplication.processEvents()

            dialog.edit_width.setFocus(_focus_reason())
            QApplication.processEvents()
            assert QApplication.focusWidget() is dialog.edit_width
            _press(Qt.Key.Key_Up)
            # The manager DELEGATES the edge key to the behind section — the
            # modal twin above never gets that grant. The grant lands inside
            # the behind window: Qt keeps app-level focus in the active window
            # (the dialog), so setFocus there moves the behind window's own
            # focus widget, not QApplication.focusWidget().
            assert behind_section.grants == ["last"]
            assert behind.focusWidget() is behind_section.anchor
        finally:
            manager.unregister(dialog)
            if dialog.isVisible():
                dialog.close()
            QApplication.processEvents()
    finally:
        manager.unregister(behind)


# ------------------------------------------------------------------
# Field-level arrow semantics
# ------------------------------------------------------------------


def test_line_edit_yields_arrows_at_caret_edge(dialog):
    """Mid-text, ←/→ move the caret (the field keeps the key); at the caret
    edge the field yields and the ring moves focus within the row."""
    dialog.edit_width.setFocus(_focus_reason())
    QApplication.processEvents()
    dialog.edit_width.setText("1234")

    dialog.edit_width.setCursorPosition(2)
    _press(Qt.Key.Key_Right)
    assert dialog.edit_width.cursorPosition() == 3
    assert QApplication.focusWidget() is dialog.edit_width

    dialog.edit_width.setCursorPosition(2)
    _press(Qt.Key.Key_Left)
    assert dialog.edit_width.cursorPosition() == 1
    assert QApplication.focusWidget() is dialog.edit_width

    # Right edge: the ring takes the key and moves to the next control.
    dialog.edit_width.setCursorPosition(4)
    _press(Qt.Key.Key_Right)
    assert QApplication.focusWidget() is dialog.btn_lock_ratio

    # Left edge of the first control: consumed at the row edge.
    dialog.edit_width.setCursorPosition(0)
    _press(Qt.Key.Key_Left)
    assert QApplication.focusWidget() is dialog.edit_width


# ------------------------------------------------------------------
# Pre-existing Space semantics
# ------------------------------------------------------------------


def test_space_shortcut_semantics_unchanged(dialog):
    """The markup must not disturb the existing Space behavior:

    * timeline focused — the dialog shortcut's guard stays silent (the
      timeline owns Space; no double toggle);
    * line edit focused — Space still types a space (the field's
      ShortcutOverride claim wins over the window-level shortcut);
    * a non-consuming focused widget — the dialog-level shortcut still
      toggles playback exactly once.
    """
    play_clicks: list[bool] = []
    dialog.playClicked.connect(lambda checked: play_clicks.append(checked))

    # Timeline: guard silent.
    dialog.timeline.setFocus(_focus_reason())
    QApplication.processEvents()
    _press(Qt.Key.Key_Space)
    assert play_clicks == []

    # Line edit: types a space.
    dialog.edit_width.setFocus(_focus_reason())
    QApplication.processEvents()
    dialog.edit_width.setText("1920")
    _press(Qt.Key.Key_Space)
    assert dialog.edit_width.text() == "1920 "
    assert play_clicks == []

    # Non-consuming widget (a button): the dialog shortcut toggles once.
    dialog.btn_trim.setFocus(_focus_reason())
    QApplication.processEvents()
    _press(Qt.Key.Key_Space)
    assert len(play_clicks) == 1
