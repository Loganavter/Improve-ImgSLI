"""Tab framework activation lifecycle — fail-closed behavior.

Activation must never diverge from the visible page (fail-closed on
``_ensure_page`` None) and must never strand the registry in a None limbo
(``on_activated`` exception restores the previous active tab). The
capability probe must isolate raising tabs (skip, not abort).

Dogma source: docs/dev/tabs/capability-mechanisms.md, docs/dev/tabs/contract.md.
"""

from __future__ import annotations

import pytest

from tabs.contract import TabContext, TabContract
from tabs.registry import TabRegistry


class _FakeStack:
    """Minimal stand-in for QStackedWidget (addWidget only)."""

    def __init__(self):
        self.widgets: list[object] = []

    def addWidget(self, widget: object) -> int:
        self.widgets.append(widget)
        return len(self.widgets) - 1


class _FakeTab(TabContract):
    def __init__(
        self,
        session_type: str,
        *,
        fail_page: bool = False,
        throw_on_activate: bool = False,
        service_payload: object = None,
        throw_on_service: bool = False,
    ):
        self._session_type = session_type
        self._fail_page = fail_page
        self._throw_on_activate = throw_on_activate
        self._service_payload = service_payload
        self._throw_on_service = throw_on_service
        self.lifecycle: list[str] = []

    @property
    def session_type(self) -> str:
        return self._session_type

    @property
    def display_name(self) -> str:
        return self._session_type

    def create_page(self, parent, context):
        if self._fail_page:
            raise RuntimeError(f"page build failed for {self._session_type}")
        return object()

    def on_activated(self, context: TabContext) -> None:
        self.lifecycle.append("activated")
        if self._throw_on_activate:
            raise RuntimeError(f"activate failed for {self._session_type}")

    def on_deactivated(self, context: TabContext) -> None:
        self.lifecycle.append("deactivated")

    def create_service(self, service_id: str, *args, **kwargs):
        if self._throw_on_service:
            raise RuntimeError(f"service probe failed on {self._session_type}")
        return self._service_payload


_ATTRS = (
    "_tabs",
    "_pages",
    "_pending_pages",
    "_context",
    "_stack",
    "_ui",
    "_active_session_type",
    "_active_session_id",
)


@pytest.fixture
def isolated_registry():
    """Give the test a blank TabRegistry singleton, restore it after."""
    registry = TabRegistry()
    missing = object()
    saved = {attr: getattr(registry, attr, missing) for attr in _ATTRS}
    registry._tabs = {}
    registry._pages = {}
    registry._pending_pages = {}
    registry._context = TabContext()
    if hasattr(registry, "_stack"):
        delattr(registry, "_stack")
    if hasattr(registry, "_ui"):
        delattr(registry, "_ui")
    registry._active_session_type = None
    registry._active_session_id = None
    try:
        yield registry
    finally:
        for attr in _ATTRS:
            value = saved[attr]
            if value is missing:
                try:
                    delattr(registry, attr)
                except AttributeError:
                    pass
            else:
                setattr(registry, attr, value)


def _with_stack(registry: TabRegistry) -> _FakeStack:
    stack = _FakeStack()
    registry._stack = stack
    return stack


def test_failed_page_activate_keeps_previous_tab_active(isolated_registry):
    """_ensure_page None with a live stack: fail-closed, previous stays."""
    _with_stack(isolated_registry)
    good = _FakeTab("good")
    bad = _FakeTab("bad", fail_page=True)
    isolated_registry._tabs = {"good": good, "bad": bad}

    isolated_registry.activate("good")
    assert isolated_registry._active_session_type == "good"

    isolated_registry.activate("bad")  # must not raise, must not switch

    assert isolated_registry._active_session_type == "good"
    assert good.lifecycle == ["activated"]  # never deactivated
    assert bad.lifecycle == []


def test_failed_page_activate_from_none_stays_none(isolated_registry):
    """First activation with a failing page: no crash, no phantom active."""
    _with_stack(isolated_registry)
    bad = _FakeTab("bad", fail_page=True)
    isolated_registry._tabs = {"bad": bad}

    isolated_registry.activate("bad")

    assert isolated_registry._active_session_type is None
    assert bad.lifecycle == []


def test_throwing_on_activated_restores_previous_tab(isolated_registry):
    """on_activated exception: previous tab restored, no None limbo."""
    _with_stack(isolated_registry)
    good = _FakeTab("good")
    flaky = _FakeTab("flaky", throw_on_activate=True)
    isolated_registry._tabs = {"good": good, "flaky": flaky}

    isolated_registry.activate("good")
    isolated_registry.activate("flaky")  # must not raise

    assert isolated_registry._active_session_type == "good"
    assert good.lifecycle == ["activated", "deactivated", "activated"]
    assert flaky.lifecycle == ["activated"]


def test_throwing_on_activated_from_none_stays_none(isolated_registry):
    """on_activated exception with no previous tab: stays None, no crash."""
    _with_stack(isolated_registry)
    flaky = _FakeTab("flaky", throw_on_activate=True)
    isolated_registry._tabs = {"flaky": flaky}

    isolated_registry.activate("flaky")

    assert isolated_registry._active_session_type is None


def test_unknown_tab_activate_is_noop(isolated_registry):
    """Activating an unregistered type never disturbs the active tab."""
    _with_stack(isolated_registry)
    good = _FakeTab("good")
    isolated_registry._tabs = {"good": good}

    isolated_registry.activate("good")
    isolated_registry.activate("nope")

    assert isolated_registry._active_session_type == "good"
    assert good.lifecycle == ["activated"]

    isolated_registry._active_session_type = None
    isolated_registry.activate("nope")
    assert isolated_registry._active_session_type is None


def test_successful_switch_deactivates_previous(isolated_registry):
    """Guards the happy path: previous deactivated exactly once, then next."""
    good = _FakeTab("good")
    second = _FakeTab("second")
    isolated_registry._tabs = {"good": good, "second": second}

    isolated_registry.activate("good")
    isolated_registry.activate("second")

    assert isolated_registry._active_session_type == "second"
    assert good.lifecycle == ["activated", "deactivated"]
    assert second.lifecycle == ["activated"]


def test_capability_probe_skips_raising_tab(isolated_registry):
    """A raising tab is isolated: the probe reaches the later tab's answer."""
    payload = object()
    raising = _FakeTab("raising", throw_on_service=True)
    good = _FakeTab("good", service_payload=payload)
    isolated_registry._tabs = {"raising": raising, "good": good}

    result = isolated_registry.create_startup_service("some.service")

    assert result is payload


def test_capability_probe_all_raising_returns_none(isolated_registry):
    """Probe where every tab raises: returns None instead of propagating."""
    isolated_registry._tabs = {
        "r1": _FakeTab("r1", throw_on_service=True),
        "r2": _FakeTab("r2", throw_on_service=True),
    }

    assert isolated_registry.create_startup_service("some.service") is None
