"""The CSD menu strip is remeasured before the first exposed frame.

Owner report (2026-10-23): the File/Help triggers in the title bar show a
different text size in the first frames than afterwards — the same class as
the tab-bar first-frame report (`inv-toolkit-tabbar-font-relayout-2026-10-14`).

The two startup guards that exist exactly for this ("final widths while still
hidden, so the first exposed frame does not remeasure and ghost «Справка»")
asked the strip for ``remasure`` — a misspelling — so ``getattr`` returned None
and neither guard ever ran. This test pins the behaviour, not the spelling:
the strip must be remeasured BEFORE ``window.show()``.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QSize

from ui.main_window.lifecycle import MainWindowStartupController


def _fake_window(calls: list[str], strip) -> SimpleNamespace:
    return SimpleNamespace(
        _application_initialized=True,  # skip the startup pipeline
        _menu_controller=SimpleNamespace(_menu_strip=strip),
        _custom_title_bar=None,
        ui=None,
        show=lambda: calls.append("show"),
        size=lambda: QSize(800, 600),
        isMaximized=lambda: False,
        layout=lambda: None,
    )


def test_menu_strip_is_remeasured_before_the_window_is_shown(qapp, monkeypatch):
    calls: list[str] = []

    def remeasure() -> None:
        calls.append("remeasure")

    window = _fake_window(calls, SimpleNamespace(remeasure=remeasure))
    monkeypatch.setattr("plugins.onboarding.host.prepare_after_show", lambda w: None)

    MainWindowStartupController().show(window)

    assert calls == ["remeasure", "show"], (
        "the CSD menu strip must be remeasured while the window is still hidden; "
        f"observed order: {calls} (a misspelled 'remasure' made this guard dead)"
    )


def test_missing_menu_strip_is_not_a_startup_error(qapp, monkeypatch):
    calls: list[str] = []
    window = _fake_window(calls, None)
    monkeypatch.setattr("plugins.onboarding.host.prepare_after_show", lambda w: None)

    MainWindowStartupController().show(window)

    assert calls == ["show"]
