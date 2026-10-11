"""Viewport store-change scope discipline (anti-regression).

A continuous, purely-visual canvas update — split-line drag, pan/zoom, or the
font/label overlay settings — MUST be emitted with a lightweight
``viewport.<sub>`` scope (see
``src/core/state_management/viewport_scopes.py``). Both store-change handlers
(``ui/presenters/main_window/state.py`` and the IC twin
``chrome_sync._on_store_state_changed``) skip those subdomains; a bare
``"viewport"`` scope instead falls through into ``handle_store_domain``, which
schedules the FULL chrome batch (file_names / combobox / ratings /
resolution / zoom_indicator / window_schedule — the last two drive the InfoHUD
glass grab+blur) on every tick.

The split-drag did this from the start (``viewport.interaction``); the
font/label settings did NOT (bare ``viewport``), so a slider drag ran the full
chrome batch every tick and dropped to 2-4 fps. This test pins the two
guarantees that stop it coming back:

1. ``LIGHTWEIGHT_VIEWPORT_SUBDOMAINS`` is the single source of truth, and both
   handlers reference it instead of a hardcoded duplicate skip-set.
2. ``apply_font_settings`` routes its setters through a lightweight subdomain
   (``viewport.overlay``), never the bare ``viewport`` domain.

AST only — no Qt, no runtime.
"""

from __future__ import annotations

import ast

from ._framework import ROOT, parse, read

_SCOPES = ROOT / "src" / "core" / "state_management" / "viewport_scopes.py"
_STATE = ROOT / "src" / "ui" / "presenters" / "main_window" / "state.py"
_CHROME = ROOT / "src" / "tabs" / "image_compare" / "use_cases" / "chrome_sync.py"
_MUTATIONS = ROOT / "src" / "plugins" / "settings" / "mutations.py"

_CONST = "LIGHTWEIGHT_VIEWPORT_SUBDOMAINS"
_EXPECTED = {"interaction", "geometry", "overlay"}


def _string_set_literals(tree: ast.Module) -> list[set[str]]:
    out: list[set[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
            vals = {
                e.value
                for e in node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            if vals:
                out.append(vals)
    return out


def _assigned_constant_value(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == _CONST:
                return node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == _CONST:
                    return node.value
    return None


def _literal_strings(value) -> set[str]:
    if value is None:
        return set()
    candidates = value.args if isinstance(value, ast.Call) else [value]
    out: set[str] = set()
    for cand in candidates:
        if isinstance(cand, (ast.Set, ast.List, ast.Tuple)):
            out |= {
                e.value
                for e in cand.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
    return out


def test_lightweight_subdomains_single_source_and_complete():
    tree = parse(_SCOPES)
    assert tree is not None, f"missing {_SCOPES}"
    members = _literal_strings(_assigned_constant_value(tree))
    missing = _EXPECTED - members
    assert not missing, f"{_CONST} lost members {sorted(missing)}"


def test_handlers_reference_the_shared_constant():
    for path in (_STATE, _CHROME):
        tree = parse(path)
        assert tree is not None, f"missing {path}"
        names = {
            n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
        }
        assert _CONST in names, (
            f"{path} no longer references {_CONST} — the store-change skip set "
            f"must come from the single source of truth, not a local copy"
        )


def test_no_hardcoded_skip_set_in_handlers():
    for path in (_STATE, _CHROME):
        tree = parse(path)
        assert tree is not None
        for literal in _string_set_literals(tree):
            assert not ({"interaction", "geometry"} <= literal), (
                f"{path} hardcodes the viewport skip-set {sorted(literal)}; "
                f"reference {_CONST} instead so the two handlers cannot drift"
            )


def test_font_settings_apply_uses_a_lightweight_subdomain():
    source = read(_MUTATIONS)
    assert "viewport.overlay" in source, (
        "apply_font_settings no longer emits on a lightweight 'viewport.overlay' "
        "scope — a font/label slider tick would again fall through into the full "
        "chrome batch (combobox/ratings/InfoHUD) every tick"
    )
