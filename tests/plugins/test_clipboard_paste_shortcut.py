"""Canvas Ctrl+V emits a paste-from-clipboard event instead of handling the
image inline — the export/paste plugin owns the actual paste via the EventBus.

Dogma source: docs/dev/ARCHITECTURE.md §Events System (decoupled publish).
"""

from __future__ import annotations
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

from events.image_label.keyboard import ImageLabelKeyboardHandler
from plugins.export.events import ExportPasteImageFromClipboardEvent

class _DummyEventBus:
    def __init__(self):
        self.emitted: list[object] = []

    def emit(self, event):
        self.emitted.append(event)

def _build_handler(event_bus):
    return SimpleNamespace(
        store=SimpleNamespace(
            viewport=SimpleNamespace(view_state=SimpleNamespace(overlay_enabled=False))
        ),
        keyboard_state_service=object(),
        event_bus=event_bus,
        preview=SimpleNamespace(
            is_active=False,
            log_preview_debug=lambda *_args, **_kwargs: None,
            restore=lambda: None,
        ),
        input_session=SimpleNamespace(
            activate=lambda *_args, **_kwargs: None,
            deactivate=lambda *_args, **_kwargs: None,
        ),
    )

def test_canvas_ctrl_v_emits_paste_event():
    event_bus = _DummyEventBus()
    keyboard = ImageLabelKeyboardHandler(_build_handler(event_bus))
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_V,
        Qt.KeyboardModifier.ControlModifier,
    )

    keyboard.handle_key_press(event)

    assert len(event_bus.emitted) == 1
    assert isinstance(event_bus.emitted[0], ExportPasteImageFromClipboardEvent)
    assert event.isAccepted()
