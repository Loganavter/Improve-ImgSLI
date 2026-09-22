"""Centralized render-throttle dogma (Phase B1 ic-render-bus).

The nine per-module ``_last_*_sig`` throttle globals that used to live
scattered across ``rhi_renderer/`` (renderer, draw_plan,
use_cases/coverage, fallback, frame_setup, lod_commit) now live behind
``tabs.image_compare.canvas.loupe_trace.throttle_emit`` — one choke
point, one stream key per former global, bit-identical skip decisions.

Pins (AST scan, no runtime):

* no module-level ``_last_*`` assignment survives anywhere under
  ``rhi_renderer/`` — ``loupe_trace.py`` (outside that tree) is the only
  home for throttle state;
* no ``global _last...`` declaration survives in the B1-owned files;
* every B1 file that makes a sig-throttled log decision routes it
  through ``throttle_emit`` imported from ``loupe_trace``
  (``use_cases/draw.py`` has no throttle site, so it is only covered by
  the no-globals scan, not the routing pin).

Deliberately out of scope (different mechanism, not module globals):
per-renderer instance attrs such as ``renderer._last_is_same_sig`` in
``use_cases/fallback.py`` and magnifier presenter ``self._last_*``
attrs in ``features/``.

Dogma source: plan-engine-tab-migration-2026-09-14 Phase B1
(ic-render-bus); ownership wall with B2 (residency) holds — this test
never names B2's files, only the turf-wide no-globals invariant.
"""

from __future__ import annotations

import ast
import re

from ._framework import ROOT, parse, read

IC_RHI_RENDERER = (
    ROOT / "src" / "tabs" / "image_compare" / "canvas" / "rhi_renderer"
)
LOUPE_TRACE = (
    ROOT / "src" / "tabs" / "image_compare" / "canvas" / "loupe_trace.py"
)

#: B1-owned files (plan "never the twain" wall: B2's residency.py,
#: use_cases/tile_residency.py and texture_parts/** are NOT listed).
B1_FILES = (
    IC_RHI_RENDERER / "renderer.py",
    IC_RHI_RENDERER / "draw_plan.py",
    IC_RHI_RENDERER / "use_cases" / "coverage.py",
    IC_RHI_RENDERER / "use_cases" / "draw.py",
    IC_RHI_RENDERER / "use_cases" / "fallback.py",
    IC_RHI_RENDERER / "use_cases" / "frame_setup.py",
    IC_RHI_RENDERER / "use_cases" / "lod_commit.py",
)

#: Files with at least one sig-throttled log decision (draw.py has none).
THROTTLED_FILES = tuple(p for p in B1_FILES if p.name != "draw.py")

_LAST_GLOBAL_RE = re.compile(r"^_last_\w+")


def _parse(path):
    tree = parse(path)
    if tree is None:
        raise SyntaxError(f"cannot parse {path}")
    return tree


def _turf_modules():
    return sorted(IC_RHI_RENDERER.rglob("*.py"))


def test_no_module_level_last_globals_in_rhi_renderer_turf():
    """The turf holds no ``_last_*`` module state — loupe_trace does."""
    offenders = []
    for path in _turf_modules():
        tree = _parse(path)
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and _LAST_GLOBAL_RE.match(
                    target.id
                ):
                    offenders.append(f"{path.name}:{node.lineno} ({target.id})")
    assert not offenders, (
        "module-level _last_* throttle state must live in loupe_trace.py, "
        "not in rhi_renderer/:\n  - " + "\n  - ".join(offenders)
    )


def test_no_global_last_declarations_in_b1_files():
    """No ``global _last...`` remains in the migrated files."""
    offenders = []
    for path in B1_FILES:
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                for name in node.names:
                    if _LAST_GLOBAL_RE.match(name):
                        offenders.append(f"{path.name}:{node.lineno} ({name})")
    assert not offenders, (
        "global _last_* declarations must be gone (route through "
        "loupe_trace.throttle_emit):\n  - " + "\n  - ".join(offenders)
    )


def _throttle_emit_names(tree: ast.Module) -> set[str]:
    """Local names bound to loupe_trace's ``throttle_emit`` (incl. aliases)."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.endswith("loupe_trace")
        ):
            for a in node.names:
                if a.name == "throttle_emit":
                    names.add(a.asname or a.name)
    return names


def _imports_throttle_emit(tree: ast.Module) -> bool:
    return bool(_throttle_emit_names(tree))


def _calls_throttle_emit(tree: ast.Module) -> bool:
    bound = _throttle_emit_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in bound:
                return True
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "throttle_emit"
            ):
                return True
    return False


def test_throttle_decisions_route_through_loupe_trace():
    """Each throttled B1 file imports + calls ``throttle_emit``."""
    for path in THROTTLED_FILES:
        tree = _parse(path)
        assert _imports_throttle_emit(tree), (
            f"{path.name} must import throttle_emit from loupe_trace "
            f"(centralized B1 throttle store)"
        )
        assert _calls_throttle_emit(tree), (
            f"{path.name} must route its sig-throttle decision through "
            f"throttle_emit (same sig tuples, same skip outcomes)"
        )


def test_loupe_trace_owns_the_central_store():
    """``loupe_trace.py`` exposes + resets the centralized throttle."""
    src = read(LOUPE_TRACE)
    assert "def throttle_emit(" in src, (
        "loupe_trace.py must define the throttle_emit choke point"
    )
    assert '"throttle_emit"' in src or "'throttle_emit'" in src, (
        "loupe_trace.py must export throttle_emit in __all__"
    )
    tree = _parse(LOUPE_TRACE)
    reset_names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "reset_loupe_trace_state"
        ):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Attribute) and sub.attr == "clear":
                    if isinstance(sub.value, ast.Name):
                        reset_names.add(sub.value.id)
    assert "_throttle_sig" in reset_names, (
        "reset_loupe_trace_state must clear the centralized _throttle_sig "
        "store (tests isolate throttle streams through it)"
    )
