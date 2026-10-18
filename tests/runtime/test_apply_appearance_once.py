"""The one appearance-apply path emits exactly **once** per apply.

``apply_appearance`` (settings application service) replaces the
comment-enforced ``scale → QSS re-push → font`` order with one documented
path: one paint freeze, one ``singleShot(0)`` resync flush, one appearance-bus
batch. The bus (``plan-ui-metrics-systemic`` P3) must therefore see a single
coalesced ``UiMetrics.changed`` carrying the axes that changed — never one
emission per producer (``UiScale`` / ``ThemeManager`` / ``UiFont``), which is
the "transforms in steps" / over-invalidation class the path exists to close.

Falsification: drop ``end_appearance()`` from ``apply_appearance`` and
``seen`` is empty (no flush); swap the batch for plain per-axis producer
emits and it holds three entries. Both make the assertions below red.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from core.state_management.reducers import SettingsReducer
from core.store import Store
from plugins.settings.application_service import SettingsApplicationService
from plugins.settings.ui_appearance import apply_appearance


def _drain(app: QApplication) -> None:
    """Real event-loop turns: ``UiMetrics`` flushes on a zero-timer."""
    for _ in range(8):
        app.processEvents()


@pytest.fixture
def bus_spy(qapp):
    """Record every appearance-bus payload; restore the scale factor after."""
    from sli_ui_toolkit.ui.managers import UiMetrics, UiScale

    metrics = UiMetrics.get_instance()
    # Drain first: a previous test's ``app.setFont`` posts an
    # ApplicationFontChange that reaches ``UiFont`` (and so the bus) a turn
    # later; absorb it before the spy starts recording.
    _drain(qapp)
    seen: list[frozenset[str]] = []
    connection = metrics.changed.connect(seen.append)
    factor_before = UiScale.get_instance().factor()
    try:
        yield seen
    finally:
        try:
            metrics.changed.disconnect(connection)
        except (RuntimeError, TypeError):
            pass
        UiScale.get_instance().set_factor(factor_before)
        _drain(qapp)


def _other_theme() -> str:
    from sli_ui_toolkit.managers import ThemeManager

    manager = ThemeManager.get_instance()
    return "light" if manager.get_current_theme() == "dark" else "dark"


def test_all_three_axes_emit_once_with_the_union(qapp, bus_spy):
    store = Store()
    result = apply_appearance(
        store, scale=1.25, theme=_other_theme(), font=True, app=qapp
    )
    _drain(qapp)

    assert bus_spy == [frozenset({"theme", "scale", "font"})], bus_spy
    assert result == frozenset({"theme", "scale", "font"})


def test_scale_only_apply_emits_scale_axis_only(qapp, bus_spy):
    store = Store()
    result = apply_appearance(store, scale=1.25, app=qapp)
    _drain(qapp)

    # No theme and no font axis: the internal QSS re-push / pinned-font resync
    # is machinery of the scale axis, not a separate change.
    assert bus_spy == [frozenset({"scale"})], bus_spy
    assert result == frozenset({"scale"})


def test_font_only_apply_emits_font_axis_only(qapp, bus_spy):
    store = Store()
    apply_appearance(store, font=True, app=qapp)
    _drain(qapp)

    assert bus_spy == [frozenset({"font"})], bus_spy


def test_no_op_scale_apply_emits_nothing(qapp, bus_spy):
    """A scale re-assert at the current factor changes no axis — no wakeup."""
    from sli_ui_toolkit.managers import UiScale

    store = Store()
    result = apply_appearance(
        store, scale=UiScale.get_instance().factor(), app=qapp
    )
    _drain(qapp)

    assert result == frozenset()
    assert bus_spy == []


class _FakeDispatcher:
    def __init__(self, store):
        self.store = store

    def dispatch(self, action, scope=None):
        self.store.settings = SettingsReducer.reduce(self.store.settings, action)


def test_settings_scale_apply_is_a_single_emission(qapp, bus_spy):
    """The settings scale path (the trap §2.7.1 chain) emits once, not once
    per producer: scale + the pinned-font re-apply land as one union.
    """
    store = Store()
    store.get_dispatcher = lambda: _FakeDispatcher(store)
    service = SettingsApplicationService(store, None, None)

    service._apply_ui_scale_settings(SimpleNamespace(ui_scale_factor=1.25))
    _drain(qapp)

    assert abs(store.settings.ui_scale_factor - 1.25) < 1e-9
    assert len(bus_spy) == 1, bus_spy
    assert bus_spy == [frozenset({"scale", "font"})], bus_spy


def test_frozen_while_applying_and_woken_after_the_freeze(qapp, qtbot):
    """Paints are frozen across the apply; the bus lands *after* the freeze.

    The producers run while the top-level's updates are off (no intermediate
    frame), and the coalesced bus emission reaches subscribers only once the
    freeze has exited — the "transforms in steps" guard and the "bus after
    suspend" contract in one probe.
    """
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.managers import UiScale
    from sli_ui_toolkit.ui.managers import UiMetrics

    host = QWidget()
    qtbot.addWidget(host)
    host.show()
    _drain(qapp)

    metrics = UiMetrics.get_instance()
    scale_updates_enabled: list[bool] = []
    bus_updates_enabled: list[bool] = []
    scale_connection = UiScale.get_instance().scale_changed.connect(
        lambda _factor: scale_updates_enabled.append(host.updatesEnabled())
    )
    bus_connection = metrics.changed.connect(
        lambda _axes: bus_updates_enabled.append(host.updatesEnabled())
    )
    try:
        apply_appearance(Store(), scale=1.25, font=True, app=qapp)
        _drain(qapp)
    finally:
        try:
            UiScale.get_instance().scale_changed.disconnect(scale_connection)
        except (RuntimeError, TypeError):
            pass
        try:
            metrics.changed.disconnect(bus_connection)
        except (RuntimeError, TypeError):
            pass
        UiScale.get_instance().set_factor(1.0)
        _drain(qapp)

    # Frozen while the producers fan out...
    assert scale_updates_enabled == [False], scale_updates_enabled
    # ...and the single bus emission arrives only after the freeze exited.
    assert bus_updates_enabled and all(bus_updates_enabled), bus_updates_enabled
