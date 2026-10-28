"""Per-tab tile policy matrix: one row per residency knob, both tabs pinned.

Nothing stated which tab owns which tile-residency policy knob, and the two
canvas tabs derive their knobs independently (image compare = IC, multi
compare = MC), so they drift silently. This contract reads the REAL
``TilePolicy`` instances (``engine.cache.tile_policy``) each surface builds with
AST parsing -- the tab renderer modules import PySide6/QRhi at module scope and
the contract tier is Qt-free and must stay fast -- and pins the current matrix,
one test per row:

==================  ===============================  =========================
knob                image_compare (IC)               multi_compare (MC)
==================  ===============================  =========================
LOD settle window   settle, LOD_FETCH_SETTLE_MS=100   immediate (no window)
GPU tile budget     2 GiB                            512 MiB
host texture cache  3 GiB (engine default)           512 MiB
texture-array cap   867 layers                       508 layers
first-paint hold    atomic hold (coverage.py)        none
coarsest-LOD pin    pin_coarsest_level(...)          none   <- LIVE DRIFT
==================  ===============================  =========================

Every row asserts BOTH sides positively (an exact value per tab, never
``ic != mc``), so a coincidence -- or a drift in either direction -- fails.
Row 6 is the live drift tracked by ``plan-tile-policy-reliability-2026-10-24``:
the table records the measured gap (MC has no pin) and the row asserts the
intended engine-wide invariant (both tabs pin), so it is red today and carries
``xfail(strict=True)`` -- green now as a recorded known red, and a failure
(XPASS) the moment MC gains the pin, which is the signal to re-pin the row
rather than let the matrix rot.

The values are read from the production expression each policy field is built
from (``LOD_FETCH_SETTLE_MS``, ``_TILE_CACHE_BUDGET_BYTES``,
``SLOT_TILE_CACHE_BUDGET_BYTES``, ``_ARRAY_CAPACITY`` ...), so row 4 keeps
evaluating the real capacity derivation instead of a copied integer -- see
``test_texture_array_capacity_matrix``. A re-typed literal where a named symbol
already exists fails ``test_policy_instances_reuse_named_symbols``.
"""

from __future__ import annotations

import ast
import functools

import pytest

from ._framework import SRC, iter_py, parse, rel

# Tab/engine module paths (dotted) that own each knob.
IC_LOD_COMMIT = "tabs.image_compare.canvas.rhi_renderer.use_cases.lod_commit"
IC_COVERAGE = "tabs.image_compare.canvas.rhi_renderer.use_cases.coverage"
IC_PIN_SITE = "tabs.image_compare.canvas.rhi_renderer.use_cases.tile_residency"
IC_RENDERER = "tabs.image_compare.canvas.rhi_renderer.renderer"
IC_RESOURCES = "tabs.image_compare.canvas.rhi_renderer.resources"
IC_RESIDENCY = "tabs.image_compare.canvas.rhi_renderer.residency"

MC_RESIDENCY = "tabs.multi_compare.scene.passes.residency"
MC_BASE_IMAGES = "tabs.multi_compare.scene.passes.base_images"
MC_RESOURCES = "tabs.multi_compare.scene.resources"

MC_ROOT = SRC / "tabs" / "multi_compare"

#: The one engine value type and the three surfaces that instantiate it.
TILE_POLICY = "engine.cache.tile_policy"
IC_POLICY_SITE = "tabs.image_compare.canvas.rhi_renderer.use_cases.fallback"
MC_POLICY_SITE = MC_BASE_IMAGES
QL_POLICY_SITE = "engine.gpu.tiled_image_view"
POLICY_NAME = "TILE_POLICY"
POLICY_TYPE = "TilePolicy"
POLICY_FIELDS = (
    "lod_mode",
    "settle_ms",
    "atomic_on_content_swap",
    "atomic_on_hires_flip",
    "atomic_on_level_change",
    "first_paint_hold",
    "pin_coarsest",
    "tile_budget_bytes",
    "host_cache_budget_bytes",
    "array_capacity",
)

#: Constants modules (single source of truth for tile sizing / budgets).
TILE_CONSTANTS = "engine.cache.tile_constants"
TILED_IMAGE_VIEW = "engine.gpu.tiled_image_view"
HOST_TEXTURE_CACHE = "engine.gpu.host_texture_cache"


# ---------------------------------------------------------------------------
# Minimal AST constant resolver.
#
# Reading values by import is not an option here: every tab renderer module
# imports PySide6/QRhi at module scope and this tier is Qt-free. The resolver
# below follows module-level assignments and ``from ... import`` aliases
# (including re-export chains such as ``residency._TILE_CACHE_BUDGET_BYTES`` ->
# ``engine.gpu.tiled_image_view``) and evaluates plain int/float arithmetic,
# string and ``None`` literals (policy modes / "no settle window"). A name it
# cannot resolve raises -- a silent fallback number would be a pinned value
# nobody read.
# ---------------------------------------------------------------------------


class _Unresolved(LookupError):
    """A name/value the resolver could not read from the real sources."""


def _module_file(module: str):
    base = SRC.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _is_package(module: str) -> bool:
    path = _module_file(module)
    return path is not None and path.name == "__init__.py"


def _import_target(node: ast.ImportFrom, module: str) -> str:
    """Absolute dotted target of a ``from ... import`` inside ``module``."""
    if not node.level:
        return node.module or ""
    parts = module.split(".")
    # ``from .x`` (level 1) starts at the importing module's own package.
    keep = len(parts) - node.level + (1 if _is_package(module) else 0)
    base = parts[:keep]
    if node.module:
        base = base + node.module.split(".")
    return ".".join(base)


@functools.lru_cache(maxsize=None)
def _module_scope(module: str) -> dict[str, tuple]:
    """Module-level bindings: name -> ('expr', node) | ('from', module, attr)."""
    path = _module_file(module)
    if path is None:
        raise _Unresolved(f"no module {module!r} under src/")
    tree = parse(path)
    if tree is None:
        raise _Unresolved(f"cannot parse {rel(path)}")
    scope: dict[str, tuple] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                scope[node.targets[0].id] = ("expr", node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.value is not None:
                scope[node.target.id] = ("expr", node.value)
        elif isinstance(node, ast.ImportFrom):
            target = _import_target(node, module)
            for alias in node.names:
                if alias.name == "*":
                    continue
                scope[alias.asname or alias.name] = ("from", target, alias.name)
    return scope


_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a ** b,
}

#: Pure engine helpers a capacity expression may call (module, attribute).
_PURE_CALLABLES = {
    "plan_array_capacity": ("engine.gpu.array_budget", "plan_array_capacity"),
    "array_layer_px": ("engine.gpu.array_draw", "array_layer_px"),
}


def _node_value(node, module: str, seen: tuple):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):  # bool is an int subclass; not a knob
            raise _Unresolved(f"bool literal in {module}")
        if node.value is None or isinstance(node.value, (int, float, str)):
            return node.value
        raise _Unresolved(f"unsupported constant in {module}: {node.value!r}")
    if isinstance(node, ast.Name):
        return _name_value(module, node.id, seen)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _node_value(node.operand, module, seen)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _node_value(node.left, module, seen)
        right = _node_value(node.right, module, seen)
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in ("min", "max") and node.args:
            values = [_node_value(arg, module, seen) for arg in node.args]
            return min(values) if node.func.id == "min" else max(values)
        # The capacity matrix gate evaluates each surface's real expression, so
        # the engine helpers those expressions call must be callable here
        # (2026-10-28: the per-tab capacity formula moved into
        # engine.gpu.array_budget, and it is sized from the shared
        # array_layer_px()).
        target = _PURE_CALLABLES.get(node.func.id)
        if target is not None:
            import importlib

            callable_ = getattr(importlib.import_module(target[0]), target[1])
            args = [_node_value(arg, module, seen) for arg in node.args]
            kwargs = {}
            for keyword in node.keywords:
                if keyword.arg is None:
                    raise _Unresolved(
                        f"**kwargs in {module}: {ast.unparse(node)!r}"
                    )
                kwargs[keyword.arg] = _node_value(
                    keyword.value, module, seen
                )
            return callable_(*args, **kwargs)
    raise _Unresolved(f"unsupported expression in {module}: {ast.unparse(node)!r}")


def _name_value(module: str, name: str, seen: tuple):
    key = (module, name)
    if key in seen:
        raise _Unresolved(f"alias cycle at {module}.{name}")
    entry = _module_scope(module).get(name)
    if entry is None:
        raise _Unresolved(f"{module}.{name} is not a module-level name")
    if entry[0] == "expr":
        return _node_value(entry[1], module, seen + (key,))
    if entry[0] == "from":
        return _name_value(entry[1], entry[2], seen + (key,))
    raise _Unresolved(f"{module}.{name} is not a value")


def _const(module: str, name: str):
    """Effective value of ``module.name``, following import/re-export chains."""
    return _name_value(module, name, ())


# ---------------------------------------------------------------------------
# Policy instances (the substrate the rows read).
# ---------------------------------------------------------------------------


def _policy_call(module: str) -> ast.Call:
    """The module-level ``TILE_POLICY = TilePolicy(...)`` call node."""
    scope = _module_scope(module)
    entry = scope.get(POLICY_NAME)
    if entry is None:
        raise _Unresolved(f"{module} has no module-level {POLICY_NAME}")
    if entry[0] != "expr" or not isinstance(entry[1], ast.Call):
        raise _Unresolved(f"{module}.{POLICY_NAME} is not a {POLICY_TYPE}(...) call")
    call = entry[1]
    if not (isinstance(call.func, ast.Name) and call.func.id == POLICY_TYPE):
        raise _Unresolved(
            f"{module}.{POLICY_NAME} is not a {POLICY_TYPE} call "
            f"(got {ast.unparse(call.func)!r})"
        )
    return call


def _policy_value(node, module: str):
    """Resolve one policy field: bool flags are legitimate here.

    ``_node_value`` refuses bool literals because every numeric knob it pins
    must be a number; ``atomic_on_*``/``first_paint_hold``/``pin_coarsest`` are
    flags, so they are read as-is (still only literals or named expressions --
    a computed bool expression is not a knob anybody can pin).
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return node.value
    return _node_value(node, module, ())


def policy_fields(module: str) -> dict[str, object]:
    """Every ``TilePolicy`` field of ``module``'s instance, values resolved.

    Raises ``_Unresolved`` rather than defaulting: a policy field the resolver
    cannot read is a pin nobody verified.
    """
    call = _policy_call(module)
    given = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
    missing = set(POLICY_FIELDS) - set(given)
    extra = set(given) - set(POLICY_FIELDS)
    if missing or extra:
        raise AssertionError(
            f"{module}.{POLICY_NAME} fields drifted from TilePolicy: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
    return {
        name: _policy_value(given[name], module)
        for name in POLICY_FIELDS
    }


def policy_field_source(module: str, field: str) -> str:
    """The unparsed production expression a policy field is built from."""
    call = _policy_call(module)
    for kw in call.keywords:
        if kw.arg == field:
            return ast.unparse(kw.value)
    raise _Unresolved(f"{module}.{POLICY_NAME} has no field {field!r}")


def _imports_policy_type(module: str) -> bool:
    tree = _tree(module)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (
            (node.module or "") == TILE_POLICY
        ):
            return any(alias.name == POLICY_TYPE for alias in node.names)
    return False


# ---------------------------------------------------------------------------
# Symbol/AST helpers (existence and wiring, not values).
# ---------------------------------------------------------------------------


def _tree(module: str):
    path = _module_file(module)
    if path is None:
        raise _Unresolved(f"no module {module!r} under src/")
    tree = parse(path)
    if tree is None:
        raise SyntaxError(f"cannot parse {rel(path)}")
    return tree


def _defines(tree: ast.Module, name: str) -> bool:
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == name
        for node in ast.walk(tree)
    )


def _imports_symbol(tree: ast.Module, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(
            alias.name == name for alias in node.names
        ):
            return True
    return False


def _references_symbol(tree: ast.Module, name: str) -> bool:
    """True when ``name`` appears as CODE (not a string/comment)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
    return False


def _from_import_locals(tree: ast.Module, name: str) -> set[str]:
    """Local bindings a module creates via ``from ... import name [as alias]``."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == name:
                    out.add(alias.asname or alias.name)
    return out


def _called_names(tree: ast.Module) -> set[str]:
    """Simple call targets: ``f()`` -> f, ``obj.m()`` -> m."""
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                out.add(func.id)
            elif isinstance(func, ast.Attribute):
                out.add(func.attr)
    return out


def _tree_for(path):
    tree = parse(path)
    if tree is None:
        raise SyntaxError(f"cannot parse {rel(path)}")
    return tree


# ---------------------------------------------------------------------------
# Rows.
# ---------------------------------------------------------------------------


def test_policy_instances_reuse_named_symbols():
    """Each derived budget/capacity field names its production symbol.

    A re-typed literal would silently survive a change to the symbol it was
    copied from, so the matrix reads the expression, not just the value.
    """
    expected = {
        (IC_POLICY_SITE, "settle_ms"): "LOD_FETCH_SETTLE_MS",
        (IC_POLICY_SITE, "tile_budget_bytes"): "_TILE_CACHE_BUDGET_BYTES",
        (IC_POLICY_SITE, "host_cache_budget_bytes"): "_HOST_TEXTURE_CACHE_BUDGET_BYTES",
        (IC_POLICY_SITE, "array_capacity"): "_ARRAY_CAPACITY",
        (MC_POLICY_SITE, "tile_budget_bytes"): "SLOT_TILE_CACHE_BUDGET_BYTES",
        (MC_POLICY_SITE, "host_cache_budget_bytes"): "SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES",
        (MC_POLICY_SITE, "array_capacity"): "_ARRAY_CAPACITY",
        (QL_POLICY_SITE, "tile_budget_bytes"): "_TILE_CACHE_BUDGET_BYTES",
        (QL_POLICY_SITE, "host_cache_budget_bytes"): (
            "DEFAULT_HOST_TEXTURE_CACHE_BUDGET_BYTES"
        ),
        (QL_POLICY_SITE, "array_capacity"): "_ARRAY_CAPACITY",
    }
    drifted = {
        (module, field): (policy_field_source(module, field), symbol)
        for (module, field), symbol in expected.items()
        if policy_field_source(module, field) != symbol
    }
    assert not drifted, (
        f"policy fields must be built from their named production symbols, "
        f"not re-typed literals: {drifted}"
    )

    for module in (IC_POLICY_SITE, MC_POLICY_SITE, QL_POLICY_SITE):
        assert _imports_policy_type(module), (
            f"{module} must import {POLICY_TYPE} from {TILE_POLICY} -- the "
            f"policy is one engine value, not a per-module lookalike"
        )


def test_lod_settle_window_is_image_compare_only():
    """IC commits an LOD level only after 100 ms of stability; MC commits now.

    IC: the policy's ``settle_ms`` resolves to ``LOD_FETCH_SETTLE_MS``
    (``engine.cache.tile_constants``, 100 ms), consumed by the IC commit path
    (``use_cases/lod_commit.py``).
    MC: the policy is ``immediate`` with no settle window at all -- it resolves
    every slot's LOD key once and commits immediately (the module says so in a
    comment, which is not a symbol).
    """
    ic_policy = policy_fields(IC_POLICY_SITE)
    mc_policy = policy_fields(MC_POLICY_SITE)

    settle_ms = _const(TILE_CONSTANTS, "LOD_FETCH_SETTLE_MS")
    assert ic_policy["lod_mode"] == "settle", (
        f"IC tile policy lod_mode drifted: {ic_policy['lod_mode']!r} "
        f"(expected 'settle')"
    )
    assert settle_ms == 100.0 and ic_policy["settle_ms"] == settle_ms, (
        f"IC LOD settle window drifted: policy settle_ms == "
        f"{ic_policy['settle_ms']!r}, LOD_FETCH_SETTLE_MS == {settle_ms!r} "
        f"(expected 100.0)"
    )

    ic_tree = _tree(IC_LOD_COMMIT)
    assert _imports_symbol(ic_tree, "LOD_FETCH_SETTLE_MS"), (
        "IC's LOD commit path must consume LOD_FETCH_SETTLE_MS "
        "(use_cases/lod_commit.py) -- the settle window is only policy if "
        "the commit path reads it"
    )
    assert _references_symbol(ic_tree, "LOD_FETCH_SETTLE_MS"), (
        "IC's LOD commit path imports LOD_FETCH_SETTLE_MS but never uses it"
    )

    assert mc_policy["lod_mode"] == "immediate", (
        f"multi_compare tile policy drifted off immediate commit: "
        f"lod_mode == {mc_policy['lod_mode']!r} (MC is the immediate-commit "
        f"tab, plan-tile-policy-reliability-2026-10-24)"
    )
    assert mc_policy["settle_ms"] is None, (
        f"multi_compare gained an LOD settle window: settle_ms == "
        f"{mc_policy['settle_ms']!r} (expected None) -- re-pin this row and "
        f"the tab-policy matrix before changing the policy"
    )
    mc_tree = _tree(MC_RESIDENCY)
    assert not _imports_symbol(mc_tree, "LOD_FETCH_SETTLE_MS"), (
        "multi_compare references LOD_FETCH_SETTLE_MS as code: MC commits LOD "
        "immediately and must not inherit IC's settle window by accident"
    )


def test_gpu_tile_budget_matrix():
    """IC grants the shared eviction pass 2 GiB; MC grants each slot pool 512 MiB."""
    ic_policy = policy_fields(IC_POLICY_SITE)
    mc_policy = policy_fields(MC_POLICY_SITE)

    ic_budget = _const(TILED_IMAGE_VIEW, "_TILE_CACHE_BUDGET_BYTES")
    mc_budget = _const(MC_RESOURCES, "SLOT_TILE_CACHE_BUDGET_BYTES")

    assert (
        ic_policy["tile_budget_bytes"] == ic_budget == 2 * 1024**3
        and mc_policy["tile_budget_bytes"] == mc_budget == 512 * 1024**2
    ), (
        f"GPU tile budget matrix drifted: IC policy "
        f"{ic_policy['tile_budget_bytes']!r} (expected 2 GiB, engine "
        f"_TILE_CACHE_BUDGET_BYTES == {ic_budget!r}), MC policy "
        f"{mc_policy['tile_budget_bytes']!r} (expected 512 MiB, "
        f"SLOT_TILE_CACHE_BUDGET_BYTES == {mc_budget!r})"
    )
    # IC's renderer-side name is an alias of the engine value, never a fork.
    assert (
        _const(IC_RESIDENCY, "_TILE_CACHE_BUDGET_BYTES") == ic_budget
    ), "IC residency must re-export the engine tile budget, not fork it"


def test_host_texture_cache_budget_matrix():
    """IC keeps 3 GiB of host QImages; MC caps its per-slot host caches at 512 MiB."""
    ic_policy = policy_fields(IC_POLICY_SITE)
    mc_policy = policy_fields(MC_POLICY_SITE)

    ic_host = _const(HOST_TEXTURE_CACHE, "DEFAULT_HOST_TEXTURE_CACHE_BUDGET_BYTES")
    mc_host = _const(MC_RESOURCES, "SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES")

    assert (
        ic_policy["host_cache_budget_bytes"] == ic_host == 3 * 1024**3
        and mc_policy["host_cache_budget_bytes"] == mc_host == 512 * 1024**2
    ), (
        f"host texture cache budget matrix drifted: IC policy "
        f"{ic_policy['host_cache_budget_bytes']!r} (expected 3 GiB, engine "
        f"DEFAULT_HOST_TEXTURE_CACHE_BUDGET_BYTES == {ic_host!r}), MC policy "
        f"{mc_policy['host_cache_budget_bytes']!r} (expected 512 MiB, "
        f"SLOT_HOST_TEXTURE_CACHE_BUDGET_BYTES == {mc_host!r})"
    )
    # IC's alias carries the engine default's EFFECTIVE value (assert the
    # value, not the alias name -- a rename must not pass silently).
    assert (
        _const(IC_RESIDENCY, "_HOST_TEXTURE_CACHE_BUDGET_BYTES") == ic_host
    ), "IC residency's host-cache budget alias diverged from the engine default"


def test_texture_array_capacity_matrix():
    """IC pre-sizes 867 array layers; MC pre-sizes 508.

    Both policies take ``array_capacity=_ARRAY_CAPACITY`` from their own module,
    and both capacities come from the engine's planner, not a tab-local
    expression (2026-10-28: a flat budget-sized array asked for 2032 layers /
    ~2.9 GB and integrated GPUs refused the allocation silently)::

        plan_array_capacity(
            layer_px=_ARRAY_LAYER_PX,
            demand_layers=tiles_per_axis ** 2 * multiplier,  # visible floor
            max_array_bytes=512 MiB,                         # per-array cap
            hard_max=DEFAULT_MAX_ARRAY_SIZE,                 # 2048 layers
        ) == min(2048, max(demand_layers, 512 MiB // layer_bytes))

    IC (resources.py) multiplies the visible floor by 3 (image1 + image2 +
    diff); MC (base_images.py) has no cross-image pairing (multiplier 1). Both
    share `_ARRAY_LAYER_PX = (LIVE_TILE_EXTENT + 2*TILE_APRON_PX)` (514 px,
    1_056_784 bytes/layer) and `_MAX_EXPECTED_CANVAS_PX = 4096`.

    The numbers below are the ones those expressions evaluate to, so a changed
    budget, tile size, apron or canvas bound fails here.
    """
    ic_policy = policy_fields(IC_POLICY_SITE)
    mc_policy = policy_fields(MC_POLICY_SITE)
    ic_capacity = ic_policy["array_capacity"]
    mc_capacity = mc_policy["array_capacity"]

    assert ic_capacity == 867 and mc_capacity == 508, (
        f"texture-array capacity matrix drifted: IC policy {ic_capacity!r} "
        f"(expected 867: 3 * 17^2 visible-tile floor beats the 508-layer / "
        f"512 MiB cap), MC policy {mc_capacity!r} "
        f"(expected 508: 512 MiB // 1_056_784)"
    )
    assert ic_capacity == _const(IC_RESOURCES, "_ARRAY_CAPACITY"), (
        "IC policy must take its capacity from resources._ARRAY_CAPACITY "
        "(the 3x derivation), not a second number"
    )
    assert mc_capacity == _const(MC_BASE_IMAGES, "_ARRAY_CAPACITY"), (
        "MC policy must take its capacity from base_images._ARRAY_CAPACITY "
        "(the 1x slot derivation), not a second number"
    )


def _mentions_hold(tree: ast.Module, name: str) -> bool:
    return (
        _defines(tree, name)
        or _imports_symbol(tree, name)
        or _references_symbol(tree, name)
    )


def test_first_paint_hold_is_image_compare_only():
    """IC holds a blank-white first paint atomically; MC has no such hold."""
    ic_policy = policy_fields(IC_POLICY_SITE)
    mc_policy = policy_fields(MC_POLICY_SITE)
    assert ic_policy["first_paint_hold"] is True, (
        "IC tile policy lost first_paint_hold (expected True)"
    )
    assert mc_policy["first_paint_hold"] is False, (
        f"multi_compare gained a first-paint hold flag "
        f"(first_paint_hold={mc_policy['first_paint_hold']!r}): IC-only policy "
        f"(plan-tile-policy-reliability-2026-10-24) -- re-pin this row"
    )

    ic_coverage = _tree(IC_COVERAGE)
    assert _defines(ic_coverage, "apply_first_paint_hold"), (
        "IC lost its first-paint hold owner "
        "(use_cases/coverage.py::apply_first_paint_hold)"
    )
    ic_renderer = _tree(IC_RENDERER)
    hold_locals = _from_import_locals(ic_renderer, "apply_first_paint_hold")
    assert hold_locals, (
        "IC renderer no longer imports apply_first_paint_hold from its "
        "coverage use-case -- the hold must be wired into render()"
    )
    assert hold_locals & _called_names(ic_renderer), (
        f"IC renderer imports the first-paint hold as {sorted(hold_locals)} "
        f"but never calls it"
    )

    mc_hold_sites = sorted(
        rel(path)
        for path in iter_py(MC_ROOT)
        if _mentions_hold(_tree_for(path), "apply_first_paint_hold")
    )
    assert mc_hold_sites == [], (
        f"multi_compare gained a first-paint hold in {mc_hold_sites}: IC-only "
        f"policy (plan-tile-policy-reliability-2026-10-24) -- re-pin this row"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "plan-tile-policy-reliability-2026-10-24 drift: multi_compare calls "
        "TileTextureService.pin_coarsest_level nowhere under "
        "src/tabs/multi_compare/, so under budget pressure it can evict the "
        "fallback-LOD baseline it samples (IC pins it from "
        "use_cases/tile_residency.py). Known red: XPASS means MC gained the "
        "pin -- verify the pinned level survives eviction, then re-pin this "
        "row and drop the marker."
    ),
)
def test_coarsest_lod_pin_matrix():
    """Both tabs must pin each source's coarsest pyramid level under eviction.

    MEASURED TODAY: only IC does. IC (``use_cases/tile_residency.py``) pins
    every realized source's deepest level after the magnifier realize, so
    finer levels filling in can never evict the low-res fallback the loupe
    samples (blur, not holes). MC resolves and evicts per slot with no
    equivalent call anywhere under ``src/tabs/multi_compare/`` -- so under
    budget pressure it can evict the very baseline it falls back to.

    This row states the intended policy (the invariant is engine-wide, not an
    IC privilege), which is why it is the LIVE DRIFT here: it fails today and
    is carried as ``xfail(strict=True)``. A green/XPASS row means MC gained
    the pin -- re-pin the matrix instead of letting the marker linger.
    """
    ic_policy = policy_fields(IC_POLICY_SITE)
    mc_policy = policy_fields(MC_POLICY_SITE)
    assert ic_policy["pin_coarsest"] is True, (
        "IC tile policy lost pin_coarsest (expected True)"
    )
    assert mc_policy["pin_coarsest"] is False, (
        f"multi_compare gained a coarsest-LOD pin flag "
        f"(pin_coarsest={mc_policy['pin_coarsest']!r}) -- pin it for real in "
        f"the pass, then re-pin this row and drop the xfail marker"
    )

    ic_tree = _tree(IC_PIN_SITE)
    assert "pin_coarsest_level" in _called_names(ic_tree), (
        "IC lost its coarsest-LOD pin: use_cases/tile_residency.py no longer "
        "calls tile_service.pin_coarsest_level(...) -- the fallback-LOD "
        "baseline becomes evictable under budget pressure"
    )

    mc_pin_sites = sorted(
        rel(path)
        for path in iter_py(MC_ROOT)
        if "pin_coarsest_level" in _called_names(_tree_for(path))
    )
    assert mc_pin_sites, (
        "coarsest-LOD pin is image_compare-only: multi_compare calls "
        "TileTextureService.pin_coarsest_level nowhere under "
        "src/tabs/multi_compare/ (IC does, from "
        "use_cases/tile_residency.py), so MC's fallback-LOD baseline stays "
        "evictable under budget pressure. Tracked by "
        "plan-tile-policy-reliability-2026-10-24; close it by pinning each "
        "slot's coarsest level after residency, then re-pin this row and drop "
        "the xfail marker"
    )
