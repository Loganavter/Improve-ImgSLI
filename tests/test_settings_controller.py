from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

from domain.types import Color
from plugins.settings.controller import SettingsController

class _RecorderStub:
    def __init__(self, *, is_recording: bool = True, is_paused: bool = False):
        self.is_recording = is_recording
        self.is_paused = is_paused
        self.capture_calls = 0

    def capture_frame(self):
        self.capture_calls += 1

def test_apply_font_settings_batches_and_captures(monkeypatch):
    store = SimpleNamespace(recorder=_RecorderStub())
    controller = SettingsController(
        store,
        settings_manager=SimpleNamespace(),
        presenter=None,
        event_bus=None,
    )
    request_calls = []
    font_apply_calls = []

    monkeypatch.setattr(
        controller.mutations,
        "apply_font_settings",
        lambda **kwargs: font_apply_calls.append(kwargs) or True,
    )
    monkeypatch.setattr(
        controller.notifier,
        "request_core_update",
        lambda: request_calls.append("requested"),
    )

    controller.apply_font_settings(
        140,
        30,
        Color(1, 2, 3, 255),
        Color(4, 5, 6, 128),
        True,
        "edges",
        75,
    )

    assert len(font_apply_calls) == 1
    assert request_calls == ["requested"]
    assert store.recorder.capture_calls == 1

def test_apply_font_settings_skips_capture_when_unchanged(monkeypatch):
    store = SimpleNamespace(recorder=_RecorderStub())
    controller = SettingsController(
        store,
        settings_manager=SimpleNamespace(),
        presenter=None,
        event_bus=None,
    )

    monkeypatch.setattr(
        controller.mutations,
        "apply_font_settings",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        controller.notifier,
        "request_core_update",
        lambda: (_ for _ in ()).throw(AssertionError("unexpected update request")),
    )

    controller.apply_font_settings(
        120,
        0,
        Color(255, 255, 255, 255),
        Color(0, 0, 0, 80),
        True,
        "edges",
        100,
    )

    assert store.recorder.capture_calls == 0
