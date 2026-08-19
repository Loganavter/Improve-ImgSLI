"""Contract: create_startup_service must not probe tabs without materialized pages.

During startup, ``create_startup_service`` probes all registered tabs by
capability.  With lazy tab initialization, a tab's page (and therefore its
UI widgets) may not exist yet.  Service factories for such tabs would receive
``tab._widget = None`` and create broken presenters (e.g. ToolbarPresenter
with ``widget=None`` → crash on ``connect_signals``).

Dogma: ``create_startup_service`` must only probe tabs whose page has been
materialized (exists in ``TabRegistry._pages``).  Tabs whose page hasn't been
created yet are skipped — their services will be created when the tab is first
shown.

Source: docs/dev/investigations/lazy-tab-initialization-plan.md
"""

from __future__ import annotations

from tabs.registry import TabRegistry


def test_startup_service_skips_tabs_without_pages():
    """create_startup_service must not call create_service on tabs whose
    page hasn't been materialized yet."""
    registry = TabRegistry()
    registry.discover()

    # install_pages defers creation — no pages materialized yet.
    # (We don't call install_pages here because it needs a real QStackedWidget.
    # The point is: _pages is empty after discover alone.)
    assert len(registry._pages) == 0, (
        "Expected _pages to be empty before install_pages — "
        "test setup is wrong"
    )

    # Spy on create_service to ensure it is NOT called for any tab.
    calls: list[str] = []
    original_create_service = TabRegistry.create_service

    def spying_create_service(self, service_id, *args, **kwargs):
        calls.append(service_id)
        return original_create_service(self, service_id, *args, **kwargs)

    TabRegistry.create_service = spying_create_service
    try:
        # Probe a service that image_compare implements.
        result = registry.create_startup_service("toolbar_presenter")
    finally:
        TabRegistry.create_service = original_create_service

    # With no pages materialized, create_service should NOT have been called.
    assert not calls, (
        "create_startup_service probed tabs whose pages don't exist. "
        f"create_service was called with: {calls}"
    )
    assert result is None


def test_startup_service_probes_tabs_with_pages():
    """create_startup_service probes tabs whose page IS materialized."""
    registry = TabRegistry()
    registry.discover()

    # Manually mark a tab as having a materialized page.
    for st in registry.registered_types:
        registry._pages[st] = object()  # fake page widget
        break

    # Now create_startup_service should probe (and potentially find a service).
    # We don't assert a specific result — just that create_service IS called.
    calls: list[str] = []
    original_create_service = TabRegistry.create_service

    def spying_create_service(self, service_id, *args, **kwargs):
        calls.append(service_id)
        return original_create_service(self, service_id, *args, **kwargs)

    TabRegistry.create_service = spying_create_service
    try:
        registry.create_startup_service("toolbar_presenter")
    finally:
        TabRegistry.create_service = original_create_service

    # At least one tab was probed (create_service was called).
    assert len(calls) > 0, (
        "create_startup_service did NOT probe any tabs even though "
        "pages were materialized"
    )
