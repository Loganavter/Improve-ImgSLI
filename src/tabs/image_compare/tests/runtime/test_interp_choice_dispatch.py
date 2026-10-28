"""The interpolation menu mutates the Store only through the Dispatcher.

Red-before (2026-10-28): ``InterpolationFlyoutController``'s two fallbacks — the
out-of-map value repair in ``show()`` and the combo-less branch of
``apply_choice()`` — spelled the write as ``setattr(host.store.viewport
.render_config, "interpolation_method", ...)`` whenever there was no dispatcher
or when ``dispatch()`` raised. That write skips the dispatcher lock, the undo
entry, dispatcher subscribers and the ``viewport`` emit, so a menu pick could
leave the loupe sampling the previous method while the panel showed the new one
— and ``tests/contracts/test_no_setattr_store_bypass.py`` had to carry four
allowlist entries (``task-transient-interp-setattr-2026-10-28``).

Sanctioned path (what these tests pin): ``SetInterpolationMethodAction`` →
``Dispatcher.dispatch(..., scope="viewport")`` → ``ImageRenderConfigReducer``
(``tabs/image_compare/state/reducers.py``), which ``replace()``s the config and
moves the movement filters with it.

Failure policy under test: a dispatcher that raises is retried once, then the
value is LEFT AS IS and the failure is logged; a Store with no dispatcher at
all is not written either. "Applied nothing, said so" beats "applied quietly,
behind the state machine's back".
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QWidget

from core.constants import AppConstants
from core.log_names import APP_LOGGER_NAME
from core.state_management.dispatcher import Dispatcher
from core.store import RenderConfig, Store
# Module import, not a call: registration is process-wide and idempotent, and
# this is the real wiring that makes ImageRenderConfigReducer answer
# SetInterpolationMethodAction on a bare Store().
import tabs.image_compare.bootstrap_reducers  # noqa: F401
from tabs.image_compare.ui.transient_interpolation import InterpolationFlyoutController

METHOD_KEYS = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
LANCZOS_INDEX = METHOD_KEYS.index("LANCZOS")


def _controller(store, widget=None, parent_widget=None):
    host = SimpleNamespace(
        parent_widget=parent_widget,
        _interp_flyout=None,
        _interp_popup_open=False,
        main_controller=None,
        store=store,
    )
    if widget is None:
        # No ``combo_interpolation``: the Find Action / headless host shape,
        # which is exactly the branch that used to write the Store directly.
        widget = SimpleNamespace(magnifier_settings_flyout=None)
    return host, InterpolationFlyoutController(SimpleNamespace(host=host), widget)


def _bare_store(current="NEAREST", dispatcher=...):
    """Minimal Store double: only what the write path reads/writes."""
    store = SimpleNamespace(
        settings=SimpleNamespace(current_language="en"),
        viewport=SimpleNamespace(
            render_config=SimpleNamespace(interpolation_method=current)
        ),
    )
    if dispatcher is not ...:
        if dispatcher is not None:
            store.get_dispatcher = lambda: dispatcher
        # ``dispatcher=None`` models a Store that HAS get_dispatcher() but
        # returns None (dispatcher not installed yet) — distinct from a Store
        # double that has no such method at all (``dispatcher`` omitted).
        else:
            store.get_dispatcher = lambda: None
    return store


def _shown_host(qtbot):
    """A real shown parent: the flyout's ``hideEvent`` needs a live window."""
    host_widget = QWidget()
    qtbot.addWidget(host_widget)
    host_widget.resize(500, 400)
    host_widget.show()
    qtbot.waitExposed(host_widget)
    panel = QWidget(host_widget)
    panel.show()
    return host_widget, panel


class _RaisingDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def dispatch(self, action, scope="viewport"):
        self.calls.append((getattr(action, "type", "?"), scope))
        raise RuntimeError("reducer exploded")


def _interp_warnings(caplog) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == APP_LOGGER_NAME and "interpolation" in record.getMessage()
    ]


# --- (a) working dispatcher: the pick applies and is announced ----------------


def test_choice_applies_through_dispatcher_and_emits_once():
    store = Store()
    dispatcher = Dispatcher(store)
    store.set_dispatcher(dispatcher)
    store.viewport.render_config = RenderConfig(interpolation_method="NEAREST")
    emitted: list[str] = []
    store.on_change(emitted.append)

    _host, controller = _controller(store)
    controller.apply_choice(LANCZOS_INDEX)

    assert store.viewport.render_config.interpolation_method == "LANCZOS"
    # The reducer keeps the loupe's movement filter in step (one filter).
    assert store.viewport.render_config.movement_interpolation_method == "LANCZOS"
    assert emitted == ["viewport"]
    assert [a.type for a in dispatcher.get_action_history()] == [
        "SET_INTERPOLATION_METHOD"
    ]


def test_out_of_map_stored_method_is_repaired_through_dispatcher(qtbot):
    store = Store()
    dispatcher = Dispatcher(store)
    store.set_dispatcher(dispatcher)
    store.viewport.render_config = RenderConfig(interpolation_method="NOT_A_METHOD")

    host_widget, panel = _shown_host(qtbot)
    host, controller = _controller(
        store,
        SimpleNamespace(magnifier_settings_panel=panel, magnifier_settings_flyout=None),
        host_widget,
    )
    controller.show()

    assert store.viewport.render_config.interpolation_method == (
        AppConstants.DEFAULT_INTERPOLATION_METHOD
    )
    assert host._interp_flyout is not None


# --- (b) raising dispatcher: nothing is written behind its back --------------


def test_choice_with_raising_dispatcher_leaves_store_untouched(caplog):
    dispatcher = _RaisingDispatcher()
    store = _bare_store("NEAREST", dispatcher=dispatcher)
    _host, controller = _controller(store)

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        controller.apply_choice(LANCZOS_INDEX)  # must not raise

    assert store.viewport.render_config.interpolation_method == "NEAREST"
    # One retry through the same (pure) action, then give up loudly.
    assert dispatcher.calls == [
        ("SET_INTERPOLATION_METHOD", "viewport"),
        ("SET_INTERPOLATION_METHOD", "viewport"),
    ]
    assert _interp_warnings(caplog), "a dropped write must leave a log line"


def test_out_of_map_method_with_raising_dispatcher_leaves_store_untouched(qtbot, caplog):
    dispatcher = _RaisingDispatcher()
    store = _bare_store("NOT_A_METHOD", dispatcher=dispatcher)

    host_widget, panel = _shown_host(qtbot)
    _host, controller = _controller(
        store,
        SimpleNamespace(magnifier_settings_panel=panel, magnifier_settings_flyout=None),
        host_widget,
    )
    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        controller.show()

    # Display-only repair: the list still opens on the default row, the Store
    # keeps the value it actually holds.
    assert store.viewport.render_config.interpolation_method == "NOT_A_METHOD"
    assert _interp_warnings(caplog)


# --- (c) no dispatcher: not applied, and said so -----------------------------


@pytest.mark.parametrize("shape", ["no_get_dispatcher", "returns_none"])
def test_choice_without_dispatcher_leaves_store_untouched(shape, caplog):
    store = _bare_store("NEAREST", dispatcher=None if shape == "returns_none" else ...)
    _host, controller = _controller(store)

    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        controller.apply_choice(LANCZOS_INDEX)  # must not raise

    assert store.viewport.render_config.interpolation_method == "NEAREST"
    assert _interp_warnings(caplog), "an unapplied pick must leave a log line"
