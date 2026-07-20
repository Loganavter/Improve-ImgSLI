"""Workspace transition mask host lookup after ui.main_window reassignment."""

from __future__ import annotations

from types import SimpleNamespace

from ui.presenters.main_window.workspace import _resolve_workspace_transition_mask


def test_resolve_transition_mask_on_main_window():
    mask = object()
    window = SimpleNamespace(_workspace_transition_mask=mask)
    presenter = SimpleNamespace(
        ui=SimpleNamespace(main_window=window),
        main_window_app=window,
    )
    found, host = _resolve_workspace_transition_mask(presenter)
    assert found is mask
    assert host is window


def test_resolve_transition_mask_migrates_from_app_host():
    mask = object()
    host = SimpleNamespace(_workspace_transition_mask=mask)
    window = SimpleNamespace(_workspace_transition_mask=None, _app_host=host)
    presenter = SimpleNamespace(
        ui=SimpleNamespace(main_window=window),
        main_window_app=window,
    )
    found, resolved = _resolve_workspace_transition_mask(presenter)
    assert found is mask
    assert resolved is window
    assert window._workspace_transition_mask is mask


def test_resolve_transition_mask_missing():
    window = SimpleNamespace()
    presenter = SimpleNamespace(
        ui=SimpleNamespace(main_window=window),
        main_window_app=window,
    )
    found, _host = _resolve_workspace_transition_mask(presenter)
    assert found is None
