"""MC load failures surface via the shared EventBus, never log-only.

Dogma source: docs/dev/plan_toast_refactor.md Phase 2 (§3.3) + internal-docs
bug-a1-multi-compare-load-silently-skips. Lives under the tab's own tests
per the root-tests no-tab-internals-leak contract.
"""

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.events import CoreErrorOccurredEvent
from tabs.multi_compare.use_cases.loading import _emit_mc_load_error


class _RecordingBus:
    """Minimal EventBus stand-in: records emitted events (SimpleNamespace style)."""

    def __init__(self):
        self.emitted = []

    def emit(self, event):
        self.emitted.append(event)


def test_mc_load_error_emit_helper_publishes_core_error_event():
    # A corrupt MC drop must surface via the shared EventBus, not vanish
    # log-only. Fake controller uses SimpleNamespace, never mocks, per
    # docs/dev/TESTING.md.
    bus = _RecordingBus()
    controller = SimpleNamespace(
        context=SimpleNamespace(event_bus=bus, main_window=None),
        translate=lambda key, default=None: default if default is not None else key,
    )
    _emit_mc_load_error(controller, "/tmp/corrupt.png", RuntimeError("bad pixels"))
    assert len(bus.emitted) == 1
    event = bus.emitted[0]
    assert isinstance(event, CoreErrorOccurredEvent)
    assert "/tmp/corrupt.png" in event.error
    assert "bad pixels" in event.error
