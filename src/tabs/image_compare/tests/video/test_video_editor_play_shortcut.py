"""Video-editor Space/play wiring: timeline.playPauseRequested reaches toggle_playback exactly once.

Chain under test (all production code, fakes only at the seams):
sections.create_timeline_scroll_area (wiring) -> VideoEditorDialog._on_play_pause_requested
(relay) -> presenter._connect_view_signals (slot) -> playback_coordinator.toggle_playback.
Plus the dialog Space-shortcut guard: while the timeline has focus the shortcut must stay
silent because the widget already consumed Space (single toggle under both Qt behaviors:
if an accepted key still reaches the shortcut map the guard skips the duplicate; if
acceptance suppresses the shortcut the guard never triggers).
"""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtGui import QKeyEvent, Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

from tabs.image_compare.plugins.video_editor.dialog import sections as sections_mod
from tabs.image_compare.plugins.video_editor.dialog.runtime import (
    focused_widget_consumes_space,
)
from tabs.image_compare.plugins.video_editor.dialog.shell import VideoEditorDialog
from tabs.image_compare.plugins.video_editor.presenter import VideoEditorPresenter
from tabs.image_compare.plugins.video_editor.widgets.timeline import (
    VideoTimelineWidget,
)

_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or _APP or QApplication([])
    return _APP


class _ViewHolder(QObject):
    destroyed = Signal()
    playClicked = Signal(bool)
    playPauseRequested = Signal()
    timelineScrubbed = Signal(int)
    undoClicked = Signal()
    redoClicked = Signal()
    trimClicked = Signal()
    exportClicked = Signal()
    stopExportClicked = Signal()
    widthChanged = Signal(int)
    heightChanged = Signal(int)
    fpsChanged = Signal(int)
    previewScaleChanged = Signal(float)
    aspectRatioLockChanged = Signal(bool)
    fitContentChanged = Signal(bool)
    fitContentFillColorChanged = Signal(object)
    containerChanged = Signal(str)
    windowResized = Signal()


def _space_press() -> QKeyEvent:
    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)


def test_sections_wires_play_pause_requested_to_dialog_handler():
    _app()
    calls: list = []
    dialog = SimpleNamespace(
        export_controller=None,
        _on_head_moved=lambda _i: None,
        _on_trim_clicked=lambda: None,
        _on_play_pause_requested=lambda: calls.append(1),
    )
    sections_mod.create_timeline_scroll_area(dialog)
    assert hasattr(dialog.timeline, "playPauseRequested")
    event = _space_press()
    dialog.timeline.keyPressEvent(event)
    assert event.isAccepted()
    assert calls == [1]


def test_shell_relay_emits_play_pause_requested_once():
    _app()
    fired: list = []

    class _Relay(QObject):
        playPauseRequested = Signal()

    relay = _Relay()
    relay.playPauseRequested.connect(lambda: fired.append(1))
    VideoEditorDialog._on_play_pause_requested(relay)
    assert fired == [1]


def _fake_presenter_calls():
    return SimpleNamespace(calls=[])


def _make_fake_presenter():
    view = _ViewHolder()
    rec = SimpleNamespace(toggles=0, seeks=[])

    def _toggle():
        rec.toggles += 1

    playback = SimpleNamespace(
        toggle_playback=_toggle,
        seek_to_frame=lambda i: rec.seeks.append(i),
        undo=lambda: None,
        redo=lambda: None,
        trim_selection=lambda: None,
        on_fps_changed=lambda _v: None,
        on_aspect_ratio_lock_changed=lambda _v: None,
    )
    export = SimpleNamespace(stop_export=lambda: None)
    preview = SimpleNamespace(
        on_width_changed=lambda _v: None,
        on_height_changed=lambda _v: None,
        on_preview_scale_changed=lambda _v: None,
        on_fit_content_changed=lambda _v: None,
        on_fit_content_fill_color_changed=lambda _v: None,
        on_window_resized=lambda: None,
    )
    output = SimpleNamespace(on_container_changed=lambda _v: None)
    thumb = SimpleNamespace(
        on_timeline_viewport_changed=lambda _s: None,
        on_timeline_zoom_changed=lambda _z: None,
        on_timeline_viewport_state_changed=lambda _s: None,
    )
    fake = SimpleNamespace(
        view=view,
        playback_coordinator=playback,
        export_coordinator=export,
        preview_coordinator=preview,
        output_coordinator=output,
        thumbnail_coordinator=thumb,
        export_video=lambda: None,
        _on_view_destroyed=lambda: None,
        _safe_disconnect=VideoEditorPresenter._safe_disconnect,
    )
    return fake, view, rec


def test_presenter_connects_play_pause_requested_to_toggle():
    _app()
    fake, view, rec = _make_fake_presenter()
    VideoEditorPresenter._connect_view_signals(fake)
    view.playPauseRequested.emit()
    assert rec.toggles == 1


def test_presenter_disconnect_drops_play_pause_requested():
    _app()
    fake, view, rec = _make_fake_presenter()
    VideoEditorPresenter._connect_view_signals(fake)
    VideoEditorPresenter._disconnect_view_signals(fake)
    view.playPauseRequested.emit()
    assert rec.toggles == 0


def test_space_guard_consumes_timeline_and_line_edits_only():
    _app()
    assert focused_widget_consumes_space(VideoTimelineWidget([], store=None)) is True
    assert focused_widget_consumes_space(QLineEdit()) is True
    assert focused_widget_consumes_space(QWidget()) is False
    assert focused_widget_consumes_space(None) is False


def test_single_toggle_by_construction():
    """Exactly one toggle per bare Space under both Qt shortcut behaviors.

    The widget accepts Space (proven here), so either the dialog shortcut never
    fires (acceptance suppresses it) or the guard skips it (guard proven above).
    Both halves together admit exactly one toggle path — no double-fire.
    """
    _app()
    tl = VideoTimelineWidget([], store=None)
    event = _space_press()
    tl.keyPressEvent(event)
    assert event.isAccepted()
    assert focused_widget_consumes_space(tl) is True
