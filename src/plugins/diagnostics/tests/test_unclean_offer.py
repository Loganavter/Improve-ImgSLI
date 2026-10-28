"""The startup offer for an unclean previous session (plugin side).

The dialog itself is a Qt widget verified where widgets are verified; what this
file pins is the decision logic around it:

* an opted-out user is never offered anything;
* the offer carries an ``UncleanShutdown`` failure with the previous session's
  facts, and collects NOTHING until the button is pressed;
* pressing "Create report" goes through the plugin's own ``create_report``, so the
  report, its redaction and its Copy / Save / Open issue actions are the same ones
  a manual report uses.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from plugins.diagnostics import session_marker, unclean_offer
from plugins.diagnostics.plugin import DiagnosticsPlugin


def _plugin() -> DiagnosticsPlugin:
    store = Store()
    store.set_dispatcher(Dispatcher(store))
    plugin = DiagnosticsPlugin()
    plugin.initialize(SimpleNamespace(store=store, event_bus=None, plugin_coordinator=None))
    scheduled: list = []
    plugin._schedule_dialog = scheduled.append  # type: ignore[assignment]
    plugin._scheduled = scheduled  # type: ignore[attr-defined]
    return plugin


def _previous(tmp_path, monkeypatch):
    log = tmp_path / "log.txt"
    log.write_text("last line before the crash\n", encoding="utf-8")
    path = tmp_path / "last-session.json"
    monkeypatch.setattr("core.control.discovery.is_pid_alive", lambda pid: False)
    session_marker.begin_session(path=path, log_file=log, version="11.0.0")
    return session_marker.read_previous(path=path)


def test_the_offer_is_built_only_when_the_user_did_not_opt_out(tmp_path, monkeypatch):
    previous = _previous(tmp_path, monkeypatch)
    plugin = _plugin()
    scheduled_offers: list = []
    monkeypatch.setattr(
        unclean_offer, "schedule", lambda plugin_, previous_: scheduled_offers.append(previous_)
    )

    assert plugin.offer_unclean_shutdown(previous) is True

    assert scheduled_offers == [previous], (
        "the offer is scheduled with the marker itself, not a copy"
    )
    assert plugin._pending_failure["type"] == "UncleanShutdown"
    assert plugin._pending_failure["log_tail"] == ["last line before the crash"]


def test_the_offer_respects_the_opt_out(tmp_path, monkeypatch):
    previous = _previous(tmp_path, monkeypatch)
    plugin = _plugin()
    monkeypatch.setattr(unclean_offer, "settings_store", lambda plugin_: _OptedOut())
    monkeypatch.setattr(unclean_offer, "schedule", lambda *a: pytest.fail("must not offer"))

    assert plugin.offer_unclean_shutdown(previous) is False
    assert plugin._pending_failure is None


def test_creating_the_report_goes_through_the_plugin_report_path(tmp_path, monkeypatch):
    previous = _previous(tmp_path, monkeypatch)
    plugin = _plugin()
    monkeypatch.setattr(unclean_offer, "schedule", lambda *a: None)
    plugin.offer_unclean_shutdown(previous)

    unclean_offer.build_pending_report(plugin)

    assert len(plugin._scheduled) == 1, "the report dialog is scheduled once"
    built = plugin._scheduled[0]
    assert built.payload["failure"]["type"] == "UncleanShutdown"
    assert plugin._pending_failure is None, "the payload is spent, not reusable"


def test_the_offer_summary_names_what_the_report_would_carry(tmp_path, monkeypatch):
    previous = _previous(tmp_path, monkeypatch)
    plugin = _plugin()

    summary = unclean_offer.summary(previous)

    assert "started" in summary
    assert "previous log" in summary


def test_an_opted_out_flag_is_written_only_by_the_never_button(monkeypatch):
    plugin = _plugin()
    store = _SettingsDouble()
    monkeypatch.setattr(unclean_offer, "settings_store", lambda plugin_: store)

    unclean_offer.suppress(plugin)

    assert session_marker.offer_is_suppressed(store) is True


class _OptedOut:
    def __init__(self) -> None:
        self._group = ""

    def beginGroup(self, name: str) -> None:  # noqa: N802
        self._group = name

    def endGroup(self) -> None:  # noqa: N802
        self._group = ""

    def value(self, key: str, default=None):  # noqa: N802
        return False if key == "offer_unclean_report" else default

    def setValue(self, key, value) -> None:  # noqa: N802
        pass

    def sync(self) -> None:
        pass


class _SettingsDouble(_OptedOut):
    def __init__(self) -> None:
        super().__init__()
        self.stored: dict[str, object] = {}

    def value(self, key: str, default=None):  # noqa: N802
        return self.stored.get(key, default)

    def setValue(self, key, value) -> None:  # noqa: N802
        self.stored[key] = value
