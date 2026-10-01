"""C: the tab layer owns no LOD/level policy (engine-pyramid-demand).

The engine owns the demand policy now: tabs ask
``engine.cache.lod.demand_level`` (the shared level pick) or the
``engine.cache.pyramid_demand.PyramidDemandService`` and never call the raw
``select_level`` math or the store's ``best_level_for_scale`` directly, and
never import ``select_level`` from ``engine.cache.lod``.

Pinned by waves D1/D5 of ``plan-engine-pyramid-demand-2026-10-01``. A new
tab-side call site must either route through ``demand_level`` /
``PyramidDemandService`` or add a documented entry to ``_ALLOW_LIST`` below
(deliberate, reviewed exception — not a silent drift).
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, parse, rel

_TABS = SRC / "tabs"

#: Raw engine LOD calls that must not appear in tab code.
_FORBIDDEN_CALLS = ("select_level", "best_level_for_scale")

#: ``rel(path) -> {allowed call names}`` for deliberate, documented exceptions.
#: Empty on purpose: the whole tab layer routes through ``demand_level``.
_ALLOW_LIST: dict[str, set[str]] = {}


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _forbidden_sites() -> list[tuple[str, int, str]]:
    sites: list[tuple[str, int, str]] = []
    for path in iter_py(_TABS):
        tree = parse(path)
        if tree is None:
            continue
        allowed = _ALLOW_LIST.get(rel(path), set())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name in _FORBIDDEN_CALLS and name not in allowed:
                sites.append((rel(path), node.lineno, name))
    return sites


def test_tabs_never_call_raw_lod_policy() -> None:
    sites = _forbidden_sites()
    assert not sites, (
        "tab code must not call select_level / best_level_for_scale directly — "
        "route through engine.cache.lod.demand_level or "
        "engine.cache.pyramid_demand.PyramidDemandService. Offenders: "
        f"{sites}"
    )


def test_tabs_do_not_import_raw_select_level() -> None:
    offenders: list[tuple[str, int]] = []
    for path in iter_py(_TABS):
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (
                node.module or ""
            ).endswith("engine.cache.lod"):
                for alias in node.names:
                    if alias.name == "select_level":
                        offenders.append((rel(path), node.lineno))
    assert not offenders, (
        f"tab code must not import select_level from engine.cache.lod: {offenders}"
    )


def test_shared_pyramid_shim_is_gone() -> None:
    """The D2 ``tabs/_shared/pyramid.py`` re-export shim is deleted; every
    former caller imports ``engine.pyramid.coordinator`` directly."""
    assert not (SRC / "tabs" / "_shared" / "pyramid.py").exists(), (
        "src/tabs/_shared/pyramid.py still exists — the D2 shim was supposed "
        "to be deleted after every caller moved to engine.pyramid.coordinator"
    )
    offenders: list[str] = []
    for root in (SRC,):
        for path in iter_py(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            if "tabs._shared.pyramid" in text or "tabs/_shared/pyramid.py" in text:
                offenders.append(rel(path))
    assert not offenders, (
        "references to the deleted tabs._shared.pyramid module remain: "
        f"{offenders}"
    )


def test_tab_layer_actually_consumes_the_shared_demand_level() -> None:
    """Non-blind sanity: the seam is wired, not just forbidden.

    If every tab-side use were deleted the two checks above would pass
    vacuously; this asserts ``demand_level`` is actually called in the tab
    layer (the D1/D5 migration target).
    """
    from engine.cache.lod import demand_level  # noqa: F401  (import smoke)

    consumers: list[str] = []
    for path in iter_py(_TABS):
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) == "demand_level":
                consumers.append(rel(path))
    assert consumers, (
        "no tab-side call site uses engine.cache.lod.demand_level — the "
        "shared demand policy is not wired"
    )
