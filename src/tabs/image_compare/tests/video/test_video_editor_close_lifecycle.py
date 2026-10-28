"""Closing the video editor must not walk into deleted C++ children.

Owner traceback (2026-10-28)::

    Error calling Python override of QDialog::closeEvent()
    shell.closeEvent -> presenter.cleanup -> thumbnails.cleanup
      -> SettleGate.cancel -> self._timer.stop()
    RuntimeError: libshiboken: Internal C++ object (PySide6.QtCore.QTimer)
    already deleted

Mechanism: ``ThumbnailCoordinator`` owns a ``SettleGate`` parented to the
presenter (``timer_parent=self`` in ``VideoEditorPresenter``), and the gate
owns its ``QTimer`` as a QObject child. ``presenter.cleanup()`` and the
``view.destroyed`` handler (``_on_view_destroyed``) both end with
``deleteLater()`` on that presenter, so once Qt processes the deletion the
presenter's children — the gate and its timer — are gone while the coordinator
still holds Python wrappers for them. A later teardown re-entry (``closeEvent``
after the presenter already tore itself down) calls ``cancel()`` on the dead
gate: every attribute lookup still answers, and the first C++ call raises.

The contract pinned here:

* ``ThumbnailCoordinator.cleanup`` (and its gate cancel/ping helpers) survive
  a gate whose C++ object — or only whose ``QTimer`` — is already deleted;
* a live gate is still cancelled (the guard must not turn teardown into a
  no-op);
* ``VideoEditorDialog.closeEvent`` closes cleanly when the presenter's C++
  object is already gone, instead of re-entering its dead coordinator tree.

The dead state is produced without waiting on a real event loop by deleting
the presenter's C++ object directly (``shiboken6.delete``) — the same state
``deleteLater()`` reaches, and the one the owner's traceback was taken in.

Falsification (pre-fix tree, this file): both dead-state tests raise
``RuntimeError: Internal C++ object ... already deleted`` from
``SettleGate.cancel``.
"""

from __future__ import annotations

import shiboken6
import pytest
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.managers import UiScale
from tabs.image_compare.plugins.video_editor.dialog.shell import VideoEditorDialog


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


def _open_editor(qapp) -> VideoEditorDialog:
    dialog = VideoEditorDialog([], _FakeExportController(), None)
    dialog.show()
    for _ in range(4):
        qapp.processEvents()
    return dialog


def _destroy(dialog) -> None:
    try:
        if shiboken6.isValid(dialog) and dialog.isVisible():
            dialog.close()
    except RuntimeError:
        pass
    QApplication.processEvents()


def _kill_presenter(dialog) -> None:
    """Reach the field state: presenter + its child timers C++-deleted."""
    presenter = dialog.presenter
    coordinator = presenter.thumbnail_coordinator
    gate = coordinator._visible_refresh
    shiboken6.delete(presenter)
    # Sanity: this is the state the crash needs — not a mock of it.
    assert not shiboken6.isValid(presenter)
    assert not shiboken6.isValid(gate)


def test_thumbnail_cleanup_survives_an_already_deleted_gate(qapp):
    dialog = _open_editor(qapp)
    coordinator = dialog.presenter.thumbnail_coordinator
    try:
        _kill_presenter(dialog)

        coordinator.cleanup()
        coordinator.cleanup()  # idempotent: closeEvent may re-enter it
    finally:
        _destroy(dialog)


def test_gate_cancel_survives_a_deleted_timer_under_a_live_gate(qapp):
    """Half-torn-down case: the gate lives, its ``QTimer`` child does not."""
    dialog = _open_editor(qapp)
    coordinator = dialog.presenter.thumbnail_coordinator
    try:
        timer = coordinator._visible_refresh._timer
        shiboken6.delete(timer)
        assert not shiboken6.isValid(timer)

        coordinator.cleanup()
    finally:
        _destroy(dialog)


def test_cleanup_still_cancels_a_live_gate(qapp):
    """The guard above must not turn teardown into a no-op."""
    dialog = _open_editor(qapp)
    coordinator = dialog.presenter.thumbnail_coordinator
    try:
        coordinator.on_timeline_viewport_changed()
        assert coordinator._visible_refresh.is_pending()

        coordinator.cleanup()
        assert not coordinator._visible_refresh.is_pending()
    finally:
        _destroy(dialog)


def test_close_event_survives_a_presenter_that_already_tore_down(qapp):
    """The owner's exact frame: ``closeEvent`` re-enters a dead presenter.

    The override is invoked directly instead of through ``close()``: PySide
    swallows exceptions raised inside a virtual override (it prints
    "Error calling Python override ..." and carries on), which is how the
    traceback reached the owner as a console error rather than a crash.
    """
    from PySide6.QtGui import QCloseEvent

    dialog = _open_editor(qapp)
    try:
        _kill_presenter(dialog)

        dialog.closeEvent(QCloseEvent())  # pre-fix: RuntimeError from cancel()
    finally:
        _destroy(dialog)


def test_close_after_a_dead_presenter_still_closes_the_window(qapp):
    from PySide6.QtGui import QCloseEvent

    dialog = _open_editor(qapp)
    try:
        _kill_presenter(dialog)

        dialog.closeEvent(QCloseEvent())
        dialog.close()
        for _ in range(3):
            qapp.processEvents()
        assert not shiboken6.isValid(dialog)
    finally:
        _destroy(dialog)


def test_normal_close_still_tears_the_presenter_down(qapp):
    dialog = _open_editor(qapp)
    presenter = dialog.presenter
    gate = presenter.thumbnail_coordinator._visible_refresh
    try:
        dialog.close()
        for _ in range(3):
            qapp.processEvents()

        # Player + settle gate die with the dialog: nothing survives the close.
        assert not shiboken6.isValid(presenter)
        assert not shiboken6.isValid(gate)
    finally:
        _destroy(dialog)
