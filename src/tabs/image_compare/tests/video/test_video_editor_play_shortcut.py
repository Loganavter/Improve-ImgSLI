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


def test_each_play_path_fires_exactly_one_toggle():
    """Relay intact: timeline-focus path and shortcut path are disjoint singles.

    ``playPauseRequested`` (widget-consumed Space, timeline focused) and
    ``playClicked`` (dialog Space shortcut, timeline NOT focused — the guard
    proven above keeps the shortcut silent otherwise) each reach
    ``toggle_playback`` exactly once; neither auto-fires the other.
    """
    _app()
    fake, view, rec = _make_fake_presenter()
    VideoEditorPresenter._connect_view_signals(fake)
    view.playPauseRequested.emit()
    assert rec.toggles == 1
    view.playClicked.emit(True)
    assert rec.toggles == 2


def test_timeline_space_reaches_toggle_exactly_once_end_to_end():
    """Full chain, production wiring only: sections -> view relay -> toggle.

    ``create_timeline_scroll_area`` wires the toolkit widget to the dialog
    relay; emitting through the relay (what ``_on_play_pause_requested``
    does) reaches the presenter's toggle exactly once.
    """
    _app()
    fake, view, rec = _make_fake_presenter()
    VideoEditorPresenter._connect_view_signals(fake)
    dialog = SimpleNamespace(
        export_controller=None,
        _on_head_moved=lambda _i: None,
        _on_trim_clicked=lambda: None,
        _on_play_pause_requested=view.playPauseRequested.emit,
    )
    sections_mod.create_timeline_scroll_area(dialog)
    event = _space_press()
    dialog.timeline.keyPressEvent(event)
    assert event.isAccepted()
    assert rec.toggles == 1


def _presenter_signal_stub():
    """QObject carrying the 10 production presenter signals (dialog side)."""
    from PySide6.QtGui import QPixmap as _QPixmap

    class _Stub(QObject):
        from PySide6.QtCore import Signal as _Signal

        previewUpdated = _Signal(_QPixmap)
        previewReady = _Signal()
        timelinePositionChanged = _Signal(int)
        playbackStateChanged = _Signal(bool)
        buttonsStateChanged = _Signal(bool, bool)
        fitContentAvailableChanged = _Signal(bool)
        thumbnailsUpdated = _Signal(object)
        exportStarted = _Signal()
        exportLog = _Signal(str)
        errorOccurred = _Signal(str)

    return _Stub()


def _dialog_slot_stub(presenter, calls):
    """Namespace shaped like the dialog side of runtime wiring."""
    return SimpleNamespace(
        presenter=presenter,
        _on_preview_updated=lambda _pix: calls.append("previewUpdated"),
        _emit_ready_to_show=lambda: calls.append("previewReady"),
        _on_timeline_position_changed=lambda _i: calls.append(
            "timelinePositionChanged"
        ),
        _on_playback_state_changed=lambda _b: calls.append("playbackStateChanged"),
        _on_buttons_state_changed=lambda _a, _b: calls.append("buttonsStateChanged"),
        _on_fit_content_available_changed=lambda _b: calls.append(
            "fitContentAvailableChanged"
        ),
        _on_thumbnails_updated=lambda _t: calls.append("thumbnailsUpdated"),
        _on_export_started=lambda: calls.append("exportStarted"),
        _on_export_log=lambda _s: calls.append("exportLog"),
        _on_error_occurred=lambda _s: calls.append("errorOccurred"),
    )


def _emit_all_presenter_signals(presenter):
    from PySide6.QtGui import QPixmap as _QPixmap

    presenter.previewUpdated.emit(_QPixmap())
    presenter.previewReady.emit()
    presenter.timelinePositionChanged.emit(0)
    presenter.playbackStateChanged.emit(False)
    presenter.buttonsStateChanged.emit(True, False)
    presenter.fitContentAvailableChanged.emit(True)
    presenter.thumbnailsUpdated.emit({})
    presenter.exportStarted.emit()
    presenter.exportLog.emit("line")
    presenter.errorOccurred.emit("boom")


def test_runtime_connect_disconnect_pairing_is_complete():
    """Static pairing proof: every runtime connect has a table entry.

    Guards future drift — a new ``d.presenter.X.connect(d._on_Y)`` without a
    ``PRESENTER_TO_DIALOG_SLOTS`` row fails here, which would otherwise leave
    a post-close slot reachable.
    """
    import inspect
    import re

    from tabs.image_compare.plugins.video_editor.dialog import runtime as runtime_mod

    source = inspect.getsource(runtime_mod.VideoEditorDialogRuntime.connect_presenter_signals)
    connected = set(
        re.findall(r"d\.presenter\.(\w+)\.connect\(d\.(\w+)\)", source)
    )
    assert connected, "connect body must wire presenter signals"
    assert set(runtime_mod.PRESENTER_TO_DIALOG_SLOTS) == connected


def test_close_reopen_leaves_no_live_connections():
    """Bidirectional disconnect: close drops all 10 slots, reopen rewires.

    Post-disconnect emissions simulate late async completions (a worker wave
    finishing after close): none may reach a dialog slot. Reconnecting (the
    reopen path) restores delivery exactly once per emit.
    """
    _app()
    from tabs.image_compare.plugins.video_editor.dialog import runtime as runtime_mod

    presenter = _presenter_signal_stub()
    calls: list = []
    dialog = _dialog_slot_stub(presenter, calls)

    runtime = runtime_mod.VideoEditorDialogRuntime(dialog)
    runtime.connect_presenter_signals()
    _emit_all_presenter_signals(presenter)
    assert len(calls) == 10, (
        "all 10 presenter→dialog slots must be live after connect"
    )

    # Close path: every slot drops, late emissions go nowhere.
    runtime.disconnect_presenter_signals()
    _emit_all_presenter_signals(presenter)
    assert len(calls) == 10

    # Reopen path: rewire once, delivery restored exactly once per emit.
    runtime.connect_presenter_signals()
    _emit_all_presenter_signals(presenter)
    assert len(calls) == 20


def test_presenter_side_disconnect_drops_all_dialog_slots():
    """Presenter.cleanup path: own signals detach from every view slot.

    Builds a REAL ``VideoEditorPresenter`` (fake view/export seams only),
    wires every production pair from ``PRESENTER_TO_DIALOG_SLOTS``, runs the
    production ``cleanup()``, then emits every signal: late async arrivals
    after close must reach nothing. The view object is kept alive by the
    test, so silence genuinely proves disconnection (not deletion).
    """
    _app()
    from PySide6.QtGui import QPixmap as _QPixmap

    from tabs.image_compare.plugins.video_editor.dialog import runtime as runtime_mod

    view = _ViewHolder()
    export_controller = SimpleNamespace(video_exporter=None)
    presenter = VideoEditorPresenter(view, [], export_controller, None)

    received: list = []
    for _, slot_name in runtime_mod.PRESENTER_TO_DIALOG_SLOTS:
        setattr(
            view,
            slot_name,
            lambda *a, _n=slot_name, **k: received.append(_n),
        )
    for signal_name, slot_name in runtime_mod.PRESENTER_TO_DIALOG_SLOTS:
        getattr(presenter, signal_name).connect(getattr(view, slot_name))

    presenter.cleanup()
    _emit_all_presenter_signals(presenter)
    assert received == []


def test_thumbnails_updated_delivers_pixmap_dict_intact():
    """HANDOFF-1: Signal(object) fanout carries QPixmap dicts intact.

    With the old ``Signal(dict)`` the QVariantMap conversion dropped every
    QPixmap value and receivers got ``{}`` (strip wipe). Emitting a real
    pixmap dict through the REAL presenter signal must arrive with keys,
    types, and pixels intact — this test fails on ``Signal(dict)``.
    """
    _app()
    from PySide6.QtGui import QPixmap, Qt

    view = _ViewHolder()
    export_controller = SimpleNamespace(video_exporter=None)
    presenter = VideoEditorPresenter(view, [], export_controller, None)

    received: list = []
    presenter.thumbnailsUpdated.connect(lambda payload: received.append(payload))

    red = QPixmap(64, 36)
    red.fill(Qt.GlobalColor.red)
    blue = QPixmap(64, 36)
    blue.fill(Qt.GlobalColor.blue)
    presenter.thumbnailsUpdated.emit({3: red, 7: blue})

    assert len(received) == 1
    assert set(received[0].keys()) == {3, 7}
    assert all(
        isinstance(pix, QPixmap) and not pix.isNull()
        for pix in received[0].values()
    )
    assert received[0][3].toImage().pixelColor(4, 4).red() > 200
    presenter.cleanup()


def _stub_recording(duration=10.0):
    class _Rec:
        def evaluate_at(self, _timestamp: float):
            return object()

        def get_duration(self) -> float:
            return duration

    return _Rec()


def test_stale_service_completion_cannot_surface(qapp, monkeypatch):
    """HANDOFF-3 decision proof: the service drops stale waves pre-emit.

    A retired generation's completion (same call the coordinator would get
    from a late worker) never emits ``thumbnailReady``; the live generation
    still delivers. Since stale cannot surface past the service, the
    presenter keeps the 2-arg ``thumbnailReady`` wiring and the coordinator
    tag stays belt-and-braces (proven next). No 3-arg signal is introduced.
    """
    from PIL import Image

    from tabs.image_compare.plugins.video_editor.services.thumbnails import (
        ThumbnailService,
    )

    service = ThumbnailService()
    # Hermetic + synchronous: no disk cache, parked pool (workers never run).
    service.set_thumbnail_disk_cache(None)
    monkeypatch.setattr(service._thread_pool, "start", lambda worker, priority=0: None)
    ready: list = []
    service.thumbnailReady.connect(lambda i, px: ready.append((i, px)))

    generation = service.generate_thumbnails(
        _stub_recording(),
        target_count=50,
        priority_indices=[0, 1, 2],
        fps=60,
    )
    assert service._pending_indices == {0, 1, 2}

    retired = service.retire_in_flight_thumbnails()
    assert retired != generation

    # Late arrival from the retired wave: dropped, nothing emitted.
    service._on_thumbnail_generated(0, None, generation)
    assert ready == []

    # Live generation still delivers a real pixmap.
    img = Image.new("RGBA", (160, 90), (255, 0, 0, 255))
    service._on_thumbnail_generated(1, img, retired)
    assert [i for i, _ in ready] == [1]
    assert not ready[0][1].isNull()
    assert (ready[0][1].width(), ready[0][1].height()) == (160, 90)


def test_coordinator_drops_stale_tagged_completion():
    """Coordinator tag is fail-closed on mismatch, fail-open on unknown.

    ``on_single_thumbnail_ready`` drops a completion whose generation tag
    mismatches the mirrored feed generation, applies the matching one, and
    applies untagged (``None`` — today's 2-arg wiring) deliveries. This is
    the belt-and-braces layer behind the service-side drop proven above.
    """
    _app()
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import Qt

    from tabs.image_compare.plugins.video_editor.presenter_parts.thumbnails import (
        ThumbnailCoordinator,
    )

    applied: dict = {}
    timeline = SimpleNamespace(
        add_thumbnail=lambda i, px: applied.__setitem__(i, px)
    )
    coordinator = ThumbnailCoordinator(
        view=SimpleNamespace(timeline=timeline),
        editor_service=SimpleNamespace(
            get_current_recording=lambda: object(),
            get_fps=lambda: 60,
            get_frame_count=lambda: 100,
        ),
        playback_engine=SimpleNamespace(get_current_frame=lambda: 0),
        thumbnail_service=SimpleNamespace(),
        emit_thumbnails_updated=lambda _t: None,
    )
    coordinator._feed_generation = 9
    pix = QPixmap(32, 18)
    pix.fill(Qt.GlobalColor.red)

    coordinator.on_single_thumbnail_ready(4, pix, generation=8)
    assert applied == {}
    coordinator.on_single_thumbnail_ready(4, pix, generation=9)
    assert set(applied) == {4}
    coordinator.on_single_thumbnail_ready(5, pix, generation=None)
    assert set(applied) == {4, 5}
