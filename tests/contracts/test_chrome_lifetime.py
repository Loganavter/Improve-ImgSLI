"""Chrome failure atomicity + lifetime (batcher / reveal / menu / transient)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _qt_presenter(qapp, **methods):
    """A live-QWidget presenter stub (passes the batcher's Qt-alive guard)."""
    from PySide6.QtWidgets import QWidget

    presenter = QWidget()
    presenter.main_window_app = None
    for name, fn in methods.items():
        setattr(presenter, name, fn)
    return presenter


def test_batcher_failure_requeues_instead_of_dropping(qapp):
    from ui.presenters.ui_update_batcher import UIUpdateBatcher

    calls: list[str] = []
    failures = {"combobox": 1}

    def _combobox():
        if failures["combobox"]:
            failures["combobox"] -= 1
            raise ValueError("boom")
        calls.append("combobox")

    presenter = _qt_presenter(
        qapp,
        _do_update_combobox_displays=_combobox,
        _do_update_resolution_labels=lambda: calls.append("resolution"),
    )
    try:
        batcher = UIUpdateBatcher(presenter)
        batcher._pending_updates = {"combobox", "resolution"}
        batcher._flush_updates()
        # The failing branch is requeued, the healthy branch still ran.
        assert "resolution" in calls
        assert "combobox" not in calls
        assert batcher._pending_updates == {"combobox"}
        batcher._flush_scheduled = False
        batcher._flush_updates()
        assert "combobox" in calls
        assert batcher._pending_updates == set()
    finally:
        presenter.deleteLater()


def test_batcher_drops_branch_after_bounded_retries(qapp, caplog):
    from ui.presenters.ui_update_batcher import UIUpdateBatcher

    def _always_fails():
        raise ValueError("always")

    presenter = _qt_presenter(qapp, _do_update_rating_displays=_always_fails)
    try:
        batcher = UIUpdateBatcher(presenter)
        # Seed once — the batcher itself requeues until the retry budget runs
        # out, then drops the branch instead of rescheduling forever.
        batcher._pending_updates = {"ratings"}
        for _ in range(6):
            batcher._flush_scheduled = False
            batcher._flush_updates()
            batcher._flush_scheduled = False
        assert batcher._pending_updates == set()
        assert "dropping branch" in caplog.text
    finally:
        presenter.deleteLater()


def test_batcher_success_clears_failure_count(qapp):
    from ui.presenters.ui_update_batcher import UIUpdateBatcher

    state = {"fail": True}

    def _flaky():
        if state["fail"]:
            raise RuntimeError("transient qt teardown")
        state["done"] = True

    presenter = _qt_presenter(qapp, _do_update_combobox_displays=_flaky)
    try:
        batcher = UIUpdateBatcher(presenter)
        batcher._pending_updates = {"combobox"}
        batcher._flush_updates()
        assert batcher._branch_failures.get("combobox") == 1
        state["fail"] = False
        batcher._flush_scheduled = False
        batcher._flush_updates()
        assert "combobox" not in batcher._branch_failures
        assert state.get("done") is True
    finally:
        presenter.deleteLater()


def test_reveal_dead_target_never_raises(qapp):
    from PySide6.QtWidgets import QWidget

    from core.actions.types import ActionTarget
    from ui.actions import reveal as reveal_module

    widget = QWidget()
    widget.deleteLater()
    qapp.processEvents()
    target = ActionTarget(widget=widget)
    # Deleted C++ object: validity check drops it before pulse, no raise.
    reveal_module.reveal_action_target(target, delay_ms=0)

    def _raise():
        raise RuntimeError("gone")

    target2 = ActionTarget(resolve_widget=_raise)
    reveal_module.reveal_action_target(target2, delay_ms=0)

    target3 = ActionTarget(
        widget=QWidget(), ensure_visible=_raise, resolve_widget=lambda: None
    )
    reveal_module.reveal_action_target(target3, delay_ms=0)


def test_reveal_pulse_exception_swallowed(qapp, monkeypatch):
    from PySide6.QtWidgets import QWidget

    from core.actions.types import ActionTarget
    from ui.actions import reveal as reveal_module

    def _raise(_widget):
        raise RuntimeError("pulse blew up")

    monkeypatch.setattr(reveal_module.widget_pulse, "pulse_widget", _raise)
    widget = QWidget()
    try:
        reveal_module.reveal_action_target(ActionTarget(widget=widget), delay_ms=0)
    finally:
        widget.deleteLater()


def test_menu_controller_shutdown_disconnects(monkeypatch):
    from ui.main_window import menu_controller as menu_module

    events = SimpleNamespace(
        connected=[], disconnected=[], language_changed=SimpleNamespace()
    )

    class _Signal:
        def connect(self, slot):
            events.connected.append(slot)

        def disconnect(self, slot):
            events.disconnected.append(slot)

    events.language_changed = _Signal()
    monkeypatch.setattr(
        menu_module, "translation_events", lambda: events
    )
    controller = menu_module.MainWindowMenuController(SimpleNamespace())
    assert len(events.connected) == 1
    controller.shutdown()
    assert events.disconnected == events.connected
    assert controller._language_connected is False
    # Idempotent — second shutdown is a no-op, never raises.
    controller.shutdown()
    assert len(events.disconnected) == 1


def test_transient_miss_key_fail_open_without_privates():
    from ui.managers.transient_ui_manager import TransientUIManager

    manager = TransientUIManager.__new__(TransientUIManager)
    assert manager._miss_key(SimpleNamespace()) == (None, frozenset())

    broken = SimpleNamespace(get_active_tab=lambda: (_ for _ in ()).throw(AttributeError("x")))
    assert manager._miss_key(broken) == (None, frozenset())


def test_transient_get_service_uses_public_active_tab(monkeypatch):
    import tabs.registry as tabs_registry
    from ui.managers.transient_ui_manager import TransientUIManager

    seen: list[str] = []

    class _StubRegistry:
        def get_active_tab(self):
            return SimpleNamespace(session_type="image_compare")

        def discover(self):
            seen.append("discover")

        def create_startup_service(self, service_id, host):
            seen.append(service_id)
            return None

    monkeypatch.setattr(tabs_registry, "TabRegistry", _StubRegistry)
    manager = TransientUIManager(SimpleNamespace())
    seen.clear()  # __init__ wiring (closing controller) may also probe.
    assert manager._get_service("flyouts") is None
    # Negative cache: second lookup does not re-probe.
    assert manager._get_service("flyouts") is None
    assert seen.count("discover") == 1
