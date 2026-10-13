"""``capture_surface`` devtool: import and ``--list`` need no X display.

The tool drives production widgets on a private X display; simply importing
it or asking for the surface catalogue must not open a display (agents call
``--list`` to discover names). Falsification: the module is new — a base
checkout has no ``src/devtools/capture_surface.py`` to import.
"""

from __future__ import annotations

import importlib

import pytest

EXPECTED_SURFACES = {
    "settings",
    "settings-keyboard",
    "gallery",
    "gallery-populated",
    "multi",
    "multi-populated",
    "session-picker",
    "onboarding",
}


@pytest.fixture
def _no_display(monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)


def test_import_does_not_need_display(_no_display):
    module = importlib.import_module("devtools.capture_surface")
    assert EXPECTED_SURFACES <= set(module.SURFACES)
    # QRhi/GL surfaces are isolated (run in an offscreen child) so a hard
    # QRhi exit cannot take the tool down.
    assert module.SURFACES["multi"].isolated
    assert module.SURFACES["multi-populated"].isolated


def test_list_enumerates_surfaces_without_display(_no_display, capsys):
    from devtools.capture_surface import main

    assert main(["--list"]) == 0
    out = capsys.readouterr().out
    for name in EXPECTED_SURFACES:
        assert name in out, f"{name} missing from --list output"


def test_missing_display_errors_clearly(_no_display, capsys):
    from devtools.capture_surface import main

    with pytest.raises(SystemExit) as exc:
        main(["settings"])
    assert exc.value.code == 2
    assert "Xvfb" in capsys.readouterr().err


def test_unknown_surface_needs_no_display(_no_display, capsys):
    from devtools.capture_surface import main

    # Unknown-surface validation happens before the display check.
    assert main(["no-such-surface"]) == 2
    assert "unknown surface" in capsys.readouterr().err
