"""Contract: the ``auto`` theme setting resolves to a concrete light/dark theme.

Covers the Flatpak/system-theme fix (public issue #25): ``auto`` must follow the
OS color scheme via the XDG portal (falling back to ``QStyleHints``), and the
probes must never break startup.
"""

from __future__ import annotations

import core.system_theme as system_theme

def test_explicit_theme_passes_through(monkeypatch):
    monkeypatch.setattr(system_theme, "detect_system_theme", lambda: "dark")
    assert system_theme.resolve_theme("light") == "light"
    assert system_theme.resolve_theme("dark") == "dark"
    assert system_theme.resolve_theme("DARK") == "dark"
    assert system_theme.resolve_theme("  Light ") == "light"

def test_auto_uses_portal_dark(monkeypatch):
    monkeypatch.setattr(system_theme, "_portal_color_scheme", lambda: "dark")
    assert system_theme.resolve_theme("auto") == "dark"

def test_auto_uses_portal_light(monkeypatch):
    monkeypatch.setattr(system_theme, "_portal_color_scheme", lambda: "light")
    assert system_theme.resolve_theme("auto") == "light"

def test_auto_falls_back_to_style_hints(monkeypatch):
    monkeypatch.setattr(system_theme, "_portal_color_scheme", lambda: None)
    monkeypatch.setattr(system_theme, "_style_hints_color_scheme", lambda: "dark")
    assert system_theme.resolve_theme("auto") == "dark"

def test_auto_defaults_to_light_when_undetectable(monkeypatch):
    monkeypatch.setattr(system_theme, "_portal_color_scheme", lambda: None)
    monkeypatch.setattr(system_theme, "_style_hints_color_scheme", lambda: None)
    assert system_theme.resolve_theme("auto") == "light"

def test_unknown_or_missing_setting_follows_system(monkeypatch):
    monkeypatch.setattr(system_theme, "_portal_color_scheme", lambda: None)
    monkeypatch.setattr(system_theme, "_style_hints_color_scheme", lambda: "dark")
    assert system_theme.resolve_theme("weird") == "dark"
    assert system_theme.resolve_theme(None) == "dark"
    assert system_theme.resolve_theme("") == "dark"

def test_portal_probe_failure_falls_back_to_style_hints(monkeypatch):
    def boom():
        raise RuntimeError("no dbus")

    monkeypatch.setattr(system_theme, "_portal_color_scheme", boom)
    monkeypatch.setattr(system_theme, "_style_hints_color_scheme", lambda: "dark")
    assert system_theme.detect_system_theme() == "dark"

def test_all_probes_failing_returns_light(monkeypatch):
    def boom():
        raise RuntimeError("no backend")

    monkeypatch.setattr(system_theme, "_portal_color_scheme", boom)
    monkeypatch.setattr(system_theme, "_style_hints_color_scheme", boom)
    assert system_theme.detect_system_theme() == "light"
