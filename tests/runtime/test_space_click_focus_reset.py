"""Focus-out resets held keys only when focus LEAVES the window.

Measured live 2026-10-22 (the owner's session, `log.txt`): holding `Space` and
clicking the Image Compare canvas never reached the magnifier gesture. The log
shows why:

    01:04:34.133  [kbd-route] Press -> GLOBAL (key=32 Space)
    01:04:34.439  [kbd-state] reset key=None pressed_keys={} space=False
    01:04:34.439  [kbd-reset] reason=event:9            (FocusOut)

The click moves focus shell -> canvas -> shell inside one window; the blanket
"any FocusOut resets" rule cleared `space_bar_pressed` before the mouse press
handler asked for it, and the following key presses were auto-repeat, which the
global handler rejects by design (`space_auto_repeat`) — so the state never came
back while the key stayed down.

The decision lives in `focus_left_the_window`: a move inside the same window is
not a context switch; a move to another window (or to nothing) still resets.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def test_focus_move_between_ancestor_and_descendant_does_not_reset(qapp):
    from events.app_event_handler import focus_move_stays_inside

    shell = QWidget()
    canvas = QWidget(shell)
    try:
        assert focus_move_stays_inside(shell, canvas) is True
        assert focus_move_stays_inside(canvas, shell) is True
        assert focus_move_stays_inside(shell, shell) is True
    finally:
        shell.close()
        shell.deleteLater()


def test_focus_move_to_an_unrelated_widget_resets(qapp):
    from events.app_event_handler import focus_move_stays_inside

    window = QWidget()
    shell = QWidget(window)
    panel = QWidget(window)
    try:
        assert focus_move_stays_inside(shell, panel) is False
    finally:
        window.close()
        window.deleteLater()


def test_focus_loss_without_a_new_owner_resets(qapp):
    from events.app_event_handler import focus_move_stays_inside

    window = QWidget()
    try:
        assert focus_move_stays_inside(window, None) is False
        assert focus_move_stays_inside(None, window) is False
    finally:
        window.close()
        window.deleteLater()
