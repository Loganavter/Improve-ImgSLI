"""CSD chrome follows a live window resize in the video editor.

Owner report (2026-10-28): "switching to maximize in the video editor kills the
whole layout — and probably everywhere we just added buttons". Measured on a
lease with an external ``xdotool windowsize`` (no maximize, no window manager):
the window grew 1216x933 → 1620x1040 and the *content* re-laid out correctly,
while the CSD chrome froze at its show-time size —
``CsdRoundedBackground [8, 8, 1200, 917]``, ``CustomTitleBar [8, 8, 1200, 36]``
(window buttons still at x=1062). Repeated resizes never catch up, so the
background is not repainted over the new area (white strip on the right), the
inspector visually disappears and the window buttons do not move.

Root cause (measured, not assumed): the toolkit's TitleBarGeometryFilter is
installed by ``decorate_dialog`` and re-fits the chrome on ``Resize`` / ``Show``
/ ``WindowStateChange``; Qt runs event filters newest-first and the timeline
widget installs *itself* on its top-level window, consuming those three event
types (the toolkit's timeline interaction filter returns True for
``obj is widget.window()``). Installed after the CSD filter, it starves it.
``VideoEditorDialog`` therefore keeps the CSD filter first (see
``_keep_csd_chrome_filter_first``).

Blast radius, measured with the same offscreen probe (window 1636 px wide):

* ``QDialog`` + ``decorate_dialog`` — chrome 1620 (tracks)
* ``ThemedDialog`` + ``decorate_dialog`` — chrome 1620 (tracks)
* ``HelpDialog`` — chrome 1620 (tracks)
* ``SettingsDialog`` — chrome 1620 (tracks)
* ``ThemedDialog`` hosting a toolkit timeline widget — chrome 1200 (frozen)
* ``VideoEditorDialog`` — chrome 784 (= its 800 px offscreen show width)

So the class of windows that regress is exactly "hosts a toolkit timeline";
today that is only this dialog (no other module in ``src/`` instantiates one).
Maximize itself needs a window manager, hence the
``LIVE-PROOF WANTED`` line in ``DONE.md`` — these tests pin the resize path
that maximize uses.

Falsification (pre-fix tree, this file): the chrome assertions below are red
with the title bar at its show-time width (784 offscreen) while the window is
1636 px wide.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.managers import UiScale
from tabs.image_compare.plugins.video_editor.dialog.shell import VideoEditorDialog

GROWN = (1620, 1040)
MID = (1500, 1000)


class _FakePresenter:
    main_controller = None


class _FakeExportController:
    store = None
    presenter = _FakePresenter()


@pytest.fixture(autouse=True)
def _scale_one(qapp):
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)


def _build_editor() -> VideoEditorDialog:
    return VideoEditorDialog([], _FakeExportController(), None)


def _pump(app, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def _destroy(dialog) -> None:
    """One close per dialog: ``WA_DeleteOnClose`` deletes during processEvents."""
    try:
        if dialog.isVisible():
            dialog.close()
        QApplication.processEvents()
    except RuntimeError:
        pass
    QApplication.processEvents()


def _chrome(dialog):
    """(title bar, background layer) — the two objects that froze."""
    return dialog._csd_title_bar, dialog._csd_bg_layer


def _assert_chrome_on_window(dialog, *, context: str) -> None:
    bar, background = _chrome(dialog)
    # The CSD band is the transparent resize margin the chrome is inset by;
    # reading it off the bar keeps the assertion independent of its value.
    band = bar.x()
    assert band == bar.y(), "the title bar must sit on the CSD band corner"
    expected = dialog.width() - 2 * band
    assert bar.width() == expected, (
        f"{context}: title bar is {bar.width()} px wide on a {dialog.width()} px "
        f"window (expected {expected}) — the chrome did not follow the resize"
    )
    assert background.width() == expected, (
        f"{context}: background is {background.width()} px wide on a "
        f"{dialog.width()} px window (expected {expected})"
    )
    assert bar.height() > 0 and background.height() > 0


def test_title_bar_and_background_follow_a_window_resize(qapp):
    dialog = _build_editor()
    try:
        dialog.show()
        _pump(qapp)
        _assert_chrome_on_window(dialog, context="after show")

        dialog.resize(*GROWN)
        _pump(qapp)
        _assert_chrome_on_window(dialog, context="after growing the window")
        # The symptom the owner saw: chrome still at the show-time width.
        assert dialog.width() > 1600
    finally:
        _destroy(dialog)


def test_chrome_keeps_up_with_repeated_resizes(qapp):
    """Owner: "repeated resizes 1500 → 1620, the chrome never catches up"."""
    dialog = _build_editor()
    try:
        dialog.show()
        _pump(qapp)

        for size in (MID, GROWN, MID, GROWN):
            dialog.resize(*size)
            _pump(qapp)
            _assert_chrome_on_window(dialog, context=f"after resize to {size}")
    finally:
        _destroy(dialog)


def test_chrome_follows_shrink_as_well(qapp):
    """A frozen-background window also means a stale, too-large chrome."""
    dialog = _build_editor()
    try:
        dialog.show()
        _pump(qapp)
        dialog.resize(*GROWN)
        _pump(qapp)

        dialog.resize(1200, 900)
        _pump(qapp)
        _assert_chrome_on_window(dialog, context="after shrinking the window")
    finally:
        _destroy(dialog)
