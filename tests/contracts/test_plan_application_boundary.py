"""Plan application boundary (eng-total R-d, decision pin -- not merge).

A supervisor recon proved on the merge base that plan APPLICATION for
legacy ``CanvasRenderPlan`` values has exactly one implementation -- the
``apply_*`` entry points in ``engine.cache.display_tier_service`` with one
thin image-compare hook-binding caller -- while
``tabs.multi_compare.services.composition_builder`` only CONSTRUCTS
``CompositionPlan`` values (single public ``build_composition_plan``, no
display-tier / apply / QRhi imports) which ``resolve_composition`` and the
shared applicator then resolve and stash behind an explicit
``composition_root`` dispatch.

This test gives that decision teeth in AST style (no runtime, mirroring
``test_passes_merged_shape.py``): construction must never drift into
application or vice versa.

* ``apply_plan_full`` / ``apply_plan_scene_only`` are defined ONLY in the
  engine display-tier service -- no second implementation may appear, and
  the IC caller stays a thin ``_service.*`` delegator.
* the builder exposes exactly one public function
  (``build_composition_plan``) and imports nothing from the application
  side (display-tier service, plan applicators, ``resolve_composition`` /
  ``apply_*`` symbols, QRhi).
* the shared ``ui.canvas_presentation`` applicator keeps the explicit
  ``composition_root`` dispatch rule (composition branch resolves + stashes,
  legacy branch delegates through the tab service boundary).
"""

from __future__ import annotations

import ast

from ._framework import ROOT, iter_py, parse, read, rel

ENGINE_APPLY = ROOT / "src" / "engine" / "cache" / "display_tier_service.py"
BUILDER = (
    ROOT / "src" / "tabs" / "multi_compare" / "services" / "composition_builder.py"
)
SHARED_APPLICATOR = ROOT / "src" / "ui" / "canvas_presentation" / "plan_applicator.py"
IC_APPLICATOR = (
    ROOT
    / "src"
    / "tabs"
    / "image_compare"
    / "canvas"
    / "presentation"
    / "plan_applicator.py"
)

_APPLY_ENTRY_POINTS = ("apply_plan_full", "apply_plan_scene_only")

# Import-side substrings the builder (construction) must never name: the
# application side (display-tier service, plan applicators) and QRhi.
_BUILDER_FORBIDDEN_IMPORT_SUBSTRINGS = (
    "display_tier",
    "plan_applicator",
    "qrhi",
)

# Imported symbol names the builder must never bind: resolvers/appliers.
_BUILDER_FORBIDDEN_IMPORT_NAMES = (
    "resolve_composition",
    "apply_canvas_render_plan",
    "apply_plan_full",
    "apply_plan_scene_only",
    "apply_render_plan_to_canvas",
)


def _parse(path):
    tree = parse(path)
    if tree is None:
        raise SyntaxError(f"cannot parse {path}")
    return tree


def _top_level_defs(tree: ast.Module) -> list[str]:
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _func_node(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == name
        ):
            return node
    return None


def _definers_of(name: str) -> list[str]:
    """Every non-test src file with a top-level ``def <name>``."""
    owners = []
    for path in iter_py(ROOT / "src"):
        if "__pycache__" in path.parts:
            continue
        tree = parse(path)
        if tree is None:
            continue
        if any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
            for node in tree.body
        ):
            owners.append(rel(path))
    return sorted(owners)


def _imported_modules(tree: ast.Module) -> list[tuple[str, int]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out


def _imported_names(tree: ast.Module) -> list[tuple[str, int]]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out.append((alias.asname or alias.name, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.asname or alias.name.split(".")[0], node.lineno))
    return out


def test_apply_entry_points_have_single_home():
    assert ENGINE_APPLY.is_file(), (
        "missing plan-application home: src/engine/cache/display_tier_service.py"
    )
    tree = _parse(ENGINE_APPLY)
    for name in ("apply_canvas_render_plan",) + _APPLY_ENTRY_POINTS:
        assert _func_node(tree, name) is not None, (
            f"engine display-tier service must define {name} "
            f"(single plan-application implementation)"
        )
    for name in _APPLY_ENTRY_POINTS:
        owners = _definers_of(name)
        assert owners == [rel(ENGINE_APPLY)], (
            f"{name} must be defined ONLY in the engine display-tier "
            f"service (construction and application stay split): {owners}"
        )


def test_ic_caller_stays_thin_hook_binding():
    assert IC_APPLICATOR.is_file(), (
        "missing thin IC caller: "
        "src/tabs/image_compare/canvas/presentation/plan_applicator.py"
    )
    tree = _parse(IC_APPLICATOR)
    assert _func_node(tree, "apply_canvas_render_plan") is not None, (
        "thin IC caller must keep the same-signature apply_canvas_render_plan "
        "delegator (hook binding lives at the call surface)"
    )
    for name in _APPLY_ENTRY_POINTS:
        assert _func_node(tree, name) is None, (
            f"thin IC caller must not define {name}: the unprefixed "
            f"implementation lives only in the engine service (this module "
            f"keeps underscore-prefixed delegators)"
        )
    modules = [mod for mod, _ in _imported_modules(tree)]
    assert any("display_tier_service" in mod for mod in modules), (
        "thin IC caller must import the engine display_tier_service "
        "(it binds hooks, never implements application)"
    )
    src = read(IC_APPLICATOR)
    assert "_service.apply_canvas_render_plan" in src, (
        "thin IC apply_canvas_render_plan must delegate to the engine "
        "service (no logic lives in the caller)"
    )
    assert "_service.apply_plan_full" in src, (
        "thin IC _apply_plan_full must delegate to the engine service"
    )
    assert "_service.apply_plan_scene_only" in src, (
        "thin IC _apply_plan_scene_only must delegate to the engine service"
    )


def test_builder_exposes_single_public_constructor():
    assert BUILDER.is_file(), (
        "missing plan-construction home: "
        "src/tabs/multi_compare/services/composition_builder.py"
    )
    tree = _parse(BUILDER)
    public = [name for name in _top_level_defs(tree) if not name.startswith("_")]
    assert public == ["build_composition_plan"], (
        f"composition_builder must expose exactly one public function "
        f"(build_composition_plan -- construction only, never application): "
        f"{public}"
    )


def test_builder_imports_nothing_apply_side():
    tree = _parse(BUILDER)
    for mod, lineno in _imported_modules(tree):
        lowered = mod.lower()
        for forbidden in _BUILDER_FORBIDDEN_IMPORT_SUBSTRINGS:
            assert forbidden not in lowered, (
                f"composition_builder imports '{mod}' (line {lineno}): "
                f"construction must not name the application side "
                f"('{forbidden}' -- no display-tier / applicator / QRhi imports)"
            )
    for name, lineno in _imported_names(tree):
        assert name not in _BUILDER_FORBIDDEN_IMPORT_NAMES, (
            f"composition_builder imports symbol '{name}' (line {lineno}): "
            f"resolvers/appliers belong to the shared applicator, never to "
            f"construction"
        )
        assert not name.startswith("apply_"), (
            f"composition_builder imports symbol '{name}' (line {lineno}): "
            f"no apply-side helpers in construction"
        )
    # NOTE: QRhi is pinned at the import level above (case-insensitive
    # module-substring scan), not as raw source text -- the module
    # docstring legitimately names QRhi among the forbidden application-side
    # categories while importing nothing from it.


def test_shared_applicator_keeps_composition_root_dispatch():
    assert SHARED_APPLICATOR.is_file(), (
        "missing shared applicator: src/ui/canvas_presentation/plan_applicator.py"
    )
    tree = _parse(SHARED_APPLICATOR)
    entry = _func_node(tree, "apply_canvas_render_plan")
    assert entry is not None, (
        "shared applicator must define apply_canvas_render_plan "
        "(the composition_root dispatch home)"
    )
    dispatch_found = False
    for node in ast.walk(entry):
        if not isinstance(node, ast.If):
            continue
        test_src = ast.unparse(node.test)
        if "composition_root" not in test_src or "is not None" not in test_src:
            continue
        body_src = "\n".join(ast.unparse(stmt) for stmt in node.body)
        if "_apply_composition_plan" in body_src:
            dispatch_found = True
    assert dispatch_found, (
        "shared apply_canvas_render_plan must keep the explicit "
        "composition_root dispatch (composition branch resolves + stashes, "
        "never merges into legacy application)"
    )
    assert any(
        isinstance(node, ast.Constant)
        and node.value == "canvas_legacy_render_plan"
        for node in ast.walk(entry)
    ), (
        "shared apply_canvas_render_plan must delegate legacy plans through "
        "the tab service boundary (canvas_legacy_render_plan -- application "
        "stays tab-owned, not inlined)"
    )
    composer = _func_node(tree, "_apply_composition_plan")
    assert composer is not None, (
        "shared applicator must keep _apply_composition_plan "
        "(resolve + stash behind the dispatch)"
    )
    composer_src = ast.unparse(composer)
    assert "resolve_composition" in composer_src, (
        "_apply_composition_plan must resolve via resolve_composition "
        "(construction values become drawable here, nowhere else)"
    )
    assert "_active_composition" in composer_src, (
        "_apply_composition_plan must stash the resolved composition on the "
        "canvas (_active_composition)"
    )
