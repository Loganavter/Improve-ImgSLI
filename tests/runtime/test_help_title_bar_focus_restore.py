"""A deferred Help focus grant never takes focus out of the CSD title bar.

Contract under test (``docs/dev/DIALOGS.md`` § CSD / custom decorations):

* the CSD title bar is a navigation section of its own
  (``register_dialog_title_bar_navigation``), so focus resting in it is live
  keyboard focus;
* the Help dialog's deferred grants — ``_focus_help_container`` (0 and 60 ms
  after show) and ``_restore_focus_after_window_change`` (0 and 60 ms after
  every page render) — repair "nothing focused yet". They must never fire *on*
  such a stop, because they run late enough to land between two key presses.

Falsification (pre-change tree, measured on this host 2026-10-28): focus the
bar's close button, call ``_focus_help_container()`` — focus is moved to
``HelpBackBar``; then the render-time restore moves it on to the hub's first
card, chain ``Button -> HelpHubPage -> help-content-host``. That is exactly the
chain ``tests/runtime/test_dialog_title_bar_nav.py`` recorded on a CI runner
(``in_bar=False``, window active, dialog 896x636) and quarantined as a
geometry-dependent "Up resolves into the content section" — it is a late timer,
not layout: the same keys walk ``Button -> WindowControlsCluster ->
CustomTitleBar`` whenever the timers have already fired.

Deliberately geometry-free: nothing here resizes the dialog, sets a scale
factor or waits for a layout, so the pinned rule cannot depend on the runner's
metrics — only on the order in which focus and the deferred grants run.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _focus_chain(limit: int = 6) -> list[str]:
    chain: list[str] = []
    node: QWidget | None = QApplication.focusWidget()
    while node is not None and len(chain) < limit:
        chain.append(type(node).__name__)
        node = node.parent()  # type: ignore[assignment]
    return chain


def _assert_focus_in_bar(bar, moment: str) -> None:
    focused = QApplication.focusWidget()
    in_bar = focused is not None and bar.isAncestorOf(focused)
    assert in_bar, (
        f"the title bar lost focus {moment} — a deferred grant must repair an "
        f"unfocused dialog, never take focus out of a live stop "
        f"(chain={_focus_chain()})"
    )


def test_a_deferred_help_grant_never_takes_focus_out_of_the_title_bar(qapp, qtbot):
    from plugins.help.dialog import HelpDialog

    dialog = HelpDialog("en", "Improve-ImgSLI")
    dialog.show()
    qtbot.waitExposed(dialog)
    qapp.processEvents()

    try:
        bar = dialog._csd_title_bar
        assert bar is not None, "the help dialog must be CSD-decorated"
        assert bar.focus_last_button() is True
        qtbot.waitUntil(
            lambda: QApplication.focusWidget() is not None
            and bar.isAncestorOf(QApplication.focusWidget()),
            timeout=5000,
        )
        assert QApplication.activeWindow() is None or QApplication.activeWindow() is dialog

        # Both deferred entry points, called directly: no timer, no geometry.
        dialog._focus_help_container()
        qapp.processEvents()
        _assert_focus_in_bar(bar, "after the show-time grant (_focus_help_container)")

        dialog._restore_focus_after_window_change()
        qapp.processEvents()
        _assert_focus_in_bar(
            bar, "after the render-time restore (_restore_focus_after_window_change)"
        )

        # And the real path that bit on the runner: a page render schedules
        # both grants 0 and 60 ms out, while the key sequence keeps running.
        dialog._render_current()
        qtbot.wait(150)
        _assert_focus_in_bar(bar, "after a page render's 0/60 ms restores fired")
    finally:
        dialog.close()
        dialog.deleteLater()
        qapp.processEvents()
