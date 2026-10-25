"""A refused AI switch opens the page that owns the permission.

Owner's rule (2026-10-25): the toolbar sparkle only chooses the judgment domain;
``AiSettings.enabled`` is the permission (the flag the metric profile, Ask-AI and
the tie-break consult). So when permission is off, clicking the AI domain must
NOT switch the view — it opens Settings on the Image Gallery — AI page, and the
switch stays where it was.

Before this, the click flipped the toggle and nothing else happened: a silent
no-op that read as a broken button.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tabs.image_gallery.ui.widget_parts import view_prefs


class _Settings:
    def __init__(self, enabled: bool):
        self.enabled = enabled


class _Store:
    def __init__(self, enabled: bool):
        self._enabled = enabled
        self.loads = 0

    def load(self):
        self.loads += 1
        return _Settings(self._enabled)


class _Controller:
    def __init__(self, enabled: bool):
        self._ai_settings_store = _Store(enabled)
        self.activated: list[str] = []

    def activate_judgment_domain(self, domain: str) -> None:
        self.activated.append(domain)


class _Toolbar:
    def __init__(self):
        self.synced: list[str] = []

    def set_judgment_domain(self, domain: str) -> None:
        self.synced.append(domain)


class _Owner:
    def __init__(self, enabled: bool):
        self._judgment_domain = "algorithms"
        self._controller = _Controller(enabled)
        self.toolbar = _Toolbar()
        self.persisted = 0

    def _persist_view_prefs(self) -> None:
        self.persisted += 1


class _Action:
    def __init__(self, log: list[str]):
        self._log = log

    def run(self) -> None:
        self._log.append("settings.page.image_gallery.ai")


class _Registry:
    def __init__(self, log: list[str]):
        self._log = log

    def get(self, action_id: str):
        return _Action(self._log) if action_id == "settings.page.image_gallery.ai" else None


@pytest.fixture
def settings_page_opened(monkeypatch):
    log: list[str] = []
    monkeypatch.setattr(
        "ui.actions.registry.get_action_registry", lambda: _Registry(log)
    )
    return log


def test_switch_to_ai_is_refused_and_opens_the_ai_settings_page(settings_page_opened):
    owner = _Owner(enabled=False)

    view_prefs._on_domain_changed(owner, "ai")

    assert owner._judgment_domain == "algorithms", "the view must not switch"
    assert owner._controller.activated == [], "no AI work may start"
    assert settings_page_opened == ["settings.page.image_gallery.ai"]
    assert owner.toolbar.synced == ["algorithms"], "the toggle is put back"
    assert owner.persisted == 0, "a refused switch is not persisted"


def test_switch_to_ai_works_when_permission_is_on(settings_page_opened):
    owner = _Owner(enabled=True)

    view_prefs._on_domain_changed(owner, "ai")

    assert owner._judgment_domain == "ai"
    assert owner._controller.activated == ["ai"]
    assert settings_page_opened == [], "no detour when AI is enabled"
    assert owner.persisted == 1


def test_algorithms_is_never_gated(settings_page_opened):
    owner = _Owner(enabled=False)

    view_prefs._on_domain_changed(owner, "algorithms")

    assert owner._judgment_domain == "algorithms"
    assert settings_page_opened == []
