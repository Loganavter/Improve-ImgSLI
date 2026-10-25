"""Merged base-images pass shape (Phase E2, passes-merge).

Pins the single merged base-images residency pass in
``src/engine/gpu/base_images_pass.py`` built on the E1 hook seam
verbatim (``test_passes_hook_conformance.py``):

* ``BaseImagesPass`` subclasses ``BaseImagesPassHookBase`` and fills in
  both tab hooks -- ``resolve_specs(ctx) -> list[ResidencySpec]`` and
  ``upload_tile(...)`` with the E1-exact parameter shapes -- from a
  bound ``BaseImagesSpecHooks`` bundle (C3 hook-bundle pattern). It adds
  no loop of its own: ``realize`` feeds the resolved specs into the
  inherited ``realize_specs`` engine loop, and ``_upload_tile`` is a
  rename-only promotion to the public seam name.
* the multi-slot swap machine survives as engine material behind hook
  impls, never as a second engine copy: ``SwapSpec`` /
  ``resolve_swap_spec`` (pure decision), ``apply_swap_spec`` (engine
  orchestration over ``SwapApplyHooks`` tab effects, including the
  fallback-LOD ordering via ``note_swap_fallback``), and
  ``backfill_plain_preview_to_array``.
* routing declarations (``stack_role`` / ``visibility``) match both tab
  base stages, so the later routing wave orders this pass identically.
* the engine file is residency-level and interface-clean: engine types
  plus the stacking-policy enums only -- no tab imports, no app-layer
  literals, no QRhi machinery.

Whole-owner accounting: exactly two files define ``BaseImagesPass`` --
the engine pass plus the multi-slot tab-hooks surface (Phase F flag-day
deleted the fixed-pair manifest; the multi-slot path stays as the hooks
home that binds tab state and delegates the moved machine to the engine
pass). This test caps the set -- no third copy may appear -- and pins
that the realize loop still has exactly one home
(``engine/cache/residency.py``).
"""

from __future__ import annotations

import ast
import re

from ._framework import ROOT, iter_py, parse, read, rel

ENGINE_PASS = ROOT / "src" / "engine" / "gpu" / "base_images_pass.py"
ENGINE_REALIZER = ROOT / "src" / "engine" / "cache" / "residency.py"

IC_RESIDENCY = (
    ROOT / "src" / "tabs" / "image_compare" / "canvas" / "rhi_renderer" / "residency.py"
)
MC_BASE_IMAGES = (
    ROOT / "src" / "tabs" / "multi_compare" / "scene" / "passes" / "base_images.py"
)
MC_RESIDENCY = (
    ROOT / "src" / "tabs" / "multi_compare" / "scene" / "passes" / "residency.py"
)

# The retired fixed-pair manifest (Phase F flag-day deleted it; the
# multi-slot path stays as the tab-hooks home).
_TAB_HOOKS_HOME = frozenset({MC_BASE_IMAGES})

# E1-verbatim seam signatures: method -> positional arg names.
_SEAM_SIGNATURES = {
    "resolve_specs": ["self", "ctx"],
    "upload_tile": [
        "self",
        "tile_service",
        "key",
        "index",
        "tile_image",
        "updates",
        "dirty_layers",
        "region",
    ],
}

_SWAP_SPEC_FIELDS = [
    "sid",
    "size",
    "old_source",
    "old_is_multi",
    "fallback_key",
    "needs_backfill",
]

_SPEC_HOOK_FIELDS = ["resolve_specs", "upload_tile"]

_SWAP_HOOK_FIELDS = [
    "forget_stale_lod",
    "note_source_applied",
    "purge_slot_srbs",
    "destroy_slot_plain_textures",
    "upload_plain_tile",
    "discard_pending_plain_cleanup",
    "backfill_plain_preview",
    "note_pending_plain_cleanup",
    "note_swap_fallback",
]

# App-layer literals the engine seal forbids (mirrors
# test_engine_no_app_imports).
_FORBIDDEN_TEXT_RES = [
    re.compile(r"tabs\.[A-Za-z_]"),
    re.compile(r"plugins\.[A-Za-z_]"),
    re.compile(r"src/tabs"),
    re.compile(r"src/plugins"),
    re.compile(r"core/store"),
    re.compile(r"core\.store"),
]


def _parse(path):
    tree = parse(path)
    if tree is None:
        raise SyntaxError(f"cannot parse {path}")
    return tree


def _method_node(tree: ast.Module, class_name: str, method: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if isinstance(stmt, ast.FunctionDef) and stmt.name == method:
                    return stmt
    return None


def _arg_names(func: ast.FunctionDef) -> list[str]:
    return [a.arg for a in func.args.args]


def _unparse(node) -> str:
    try:
        return ast.unparse(node).strip()
    except Exception:
        return ""


def _class_bases(tree: ast.Module, class_name: str) -> list[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [_unparse(b) for b in node.bases]
    return []


def _class_attr_value(tree: ast.Module, class_name: str, attr: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and stmt.targets[0].id == attr
                    and isinstance(stmt.value, ast.Attribute)
                    and isinstance(stmt.value.value, ast.Name)
                ):
                    return (stmt.value.value.id, stmt.value.attr)
    return None


def _dataclass_fields(tree: ast.Module, class_name: str) -> list[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields = []
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.append(stmt.target.id)
            return fields
    return []


def _calls_self(tree: ast.Module, class_name: str, method: str, target: str) -> bool:
    func = _method_node(tree, class_name, method)
    if func is None:
        return False
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == target
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
        ):
            return True
    return False


def test_engine_pass_fills_seam_verbatim():
    assert ENGINE_PASS.is_file(), (
        "missing merged base-images pass: src/engine/gpu/base_images_pass.py"
    )
    tree = _parse(ENGINE_PASS)
    assert "BaseImagesPassHookBase" in _class_bases(tree, "BaseImagesPass"), (
        "engine BaseImagesPass must subclass the E1 BaseImagesPassHookBase"
    )
    for method, expected in _SEAM_SIGNATURES.items():
        func = _method_node(tree, "BaseImagesPass", method)
        assert func is not None, (
            f"engine BaseImagesPass must define {method}{tuple(expected)} "
            f"(E1 seam verbatim)"
        )
        assert _arg_names(func) == expected, (
            f"engine BaseImagesPass.{method} signature drift: expected "
            f"{expected}, got {_arg_names(func)}"
        )
    resolve = _method_node(tree, "BaseImagesPass", "resolve_specs")
    assert _unparse(resolve.returns) == "list[ResidencySpec]", (
        f"engine resolve_specs must return list[ResidencySpec], got "
        f"{_unparse(resolve.returns)!r}"
    )
    upload = _method_node(tree, "BaseImagesPass", "upload_tile")
    assert isinstance(upload.returns, ast.Constant) and upload.returns.value is None, (
        "engine seam upload_tile must return None"
    )


def test_engine_pass_adds_no_loop():
    tree = _parse(ENGINE_PASS)
    defined = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert "realize_specs" not in defined, (
        "engine BaseImagesPass must not define realize_specs: the loop is "
        "owned by TileResidencyRealizerBase.realize_specs (single home)"
    )
    realize = _method_node(tree, "BaseImagesPass", "realize")
    assert realize is not None, (
        "engine BaseImagesPass must define the realize feed "
        "(resolve -> realize_specs -> return)"
    )
    assert _calls_self(tree, "BaseImagesPass", "realize", "realize_specs"), (
        "engine realize must feed the inherited realize_specs loop "
        "(no second loop)"
    )
    resolve_fn = _method_node(tree, "BaseImagesPass", "resolve_specs")
    assert any(
        isinstance(node, ast.Call)
        and _unparse(node.func) == "self._hooks.resolve_specs"
        for node in ast.walk(resolve_fn)
    ), (
        "engine resolve_specs must delegate to the bound spec hooks "
        "(tab model, C3 bundle pattern)"
    )
    assert _method_node(tree, "BaseImagesPass", "_upload_tile") is not None, (
        "engine pass must keep the _upload_tile realizer override"
    )
    assert _calls_self(tree, "BaseImagesPass", "_upload_tile", "upload_tile"), (
        "_upload_tile must be a rename-only promotion to the public "
        "seam name (identical parameter shape per E1)"
    )


def test_swap_material_merged_behind_hooks():
    tree = _parse(ENGINE_PASS)
    assert _dataclass_fields(tree, "SwapSpec") == _SWAP_SPEC_FIELDS, (
        f"SwapSpec fields drift: got {_dataclass_fields(tree, 'SwapSpec')} "
        f"(swap decision is engine material)"
    )
    swap_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "resolve_swap_spec":
            swap_fn = node
    assert swap_fn is not None, "engine must own resolve_swap_spec"
    assert _arg_names(swap_fn) == ["slot_pixel_sources", "tile_service", "sid", "source"], (
        f"resolve_swap_spec signature drift: got {_arg_names(swap_fn)}"
    )
    assert _unparse(swap_fn.returns) == "SwapSpec | None", (
        f"resolve_swap_spec must return SwapSpec | None, got "
        f"{_unparse(swap_fn.returns)!r}"
    )
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "apply_swap_spec"
        for node in ast.walk(tree)
    ), "engine must own apply_swap_spec orchestration"
    assert any(
        isinstance(node, ast.FunctionDef)
        and node.name == "backfill_plain_preview_to_array"
        for node in ast.walk(tree)
    ), "engine must own the preview-backfill reaction"
    assert _dataclass_fields(tree, "BaseImagesSpecHooks") == _SPEC_HOOK_FIELDS, (
        "BaseImagesSpecHooks must carry exactly the E1 seam collaborators"
    )
    assert _dataclass_fields(tree, "SwapApplyHooks") == _SWAP_HOOK_FIELDS, (
        f"SwapApplyHooks fields drift: got "
        f"{_dataclass_fields(tree, 'SwapApplyHooks')} (tab effects behind "
        f"the engine orchestration, including note_swap_fallback)"
    )


def test_engine_pass_interface_clean():
    src = read(ENGINE_PASS)
    for rx in _FORBIDDEN_TEXT_RES:
        assert not rx.search(src), (
            f"engine pass matches app-layer literal {rx.pattern!r} "
            f"(engine never names its callers)"
        )
    assert "QRhi" not in src, (
        "engine pass must stay residency-level (no QRhi machinery -- "
        "GPU work stays in the resource owners)"
    )
    tree = _parse(ENGINE_PASS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            # ``core.log_names`` is the zero-dependency naming constant every
            # module uses for the app logger (logging identity, not app-layer
            # behavior — it imports nothing and touches no Store/Qt type).
            assert top in (
                "__future__",
                "dataclasses",
                "logging",
                "typing",
                "engine",
                "ui",
                "PySide6",
            ) or node.module == "core.log_names", (
                f"engine pass imports '{node.module}' (line {node.lineno}): "
                f"engine modules, stacking-policy enums, and Qt types only"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in ("logging",), (
                    f"engine pass imports '{alias.name}': stdlib only"
                )


def test_routing_role_parity_with_both_tabs():
    tree = _parse(ENGINE_PASS)
    role = _class_attr_value(tree, "BaseImagesPass", "stack_role")
    assert role == ("CanvasStackRole", "IMAGE_OVERLAY_CONTENT"), (
        f"engine BaseImagesPass.stack_role must declare the shared base "
        f"role, got {role}"
    )
    visibility = _class_attr_value(tree, "BaseImagesPass", "visibility")
    assert visibility == ("SceneVisibility", "ALL"), (
        f"engine BaseImagesPass.visibility must stay explicit ALL, got "
        f"{visibility}"
    )
    tab_tree = _parse(MC_BASE_IMAGES)
    assert _class_attr_value(tab_tree, "BaseImagesPass", "stack_role") == role, (
        f"multi_compare hooks stack_role drifted from the merged pass role"
    )
    assert _class_attr_value(tab_tree, "BaseImagesPass", "visibility") == visibility, (
        f"multi_compare hooks visibility drifted from the merged pass scope"
    )


def test_realize_loop_has_single_home():
    owners = []
    for path in iter_py(ROOT / "src"):
        if "__pycache__" in path.parts:
            continue
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for stmt in node.body:
                    if (
                        isinstance(stmt, ast.FunctionDef)
                        and stmt.name == "realize_specs"
                    ):
                        owners.append(f"{rel(path)}:{node.name}")
    assert owners == [f"{rel(ENGINE_REALIZER)}:TileResidencyRealizerBase"], (
        f"realize_specs must have exactly one home (no second engine "
        f"copies): {owners}"
    )
    for path in (IC_RESIDENCY, MC_RESIDENCY):
        tree = _parse(path)
        for cls in ("TileResidencyRealizer", "_SlotUploadRealizer"):
            assert _method_node(tree, cls, "realize_specs") is None, (
                f"{rel(path)}.{cls} defines realize_specs: tabs only "
                f"resolve specs + upload tiles"
            )


def test_base_images_pass_definitions_capped():
    """Exactly two BaseImagesPass definitions: the engine pass plus the
    multi-slot tab-hooks surface (which binds tab state and delegates the
    moved swap/residency machine to the engine pass -- no second
    implementation). No third copy may appear."""
    definers = set()
    for path in iter_py(ROOT / "src"):
        if "__pycache__" in path.parts or "tests" in path.parts:
            continue
        tree = parse(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "BaseImagesPass":
                definers.add(path)
    assert definers == ({ENGINE_PASS} | set(_TAB_HOOKS_HOME)), (
            "BaseImagesPass definitions changed: "
            f"{sorted(rel(p) for p in definers)} (engine pass + the "
            f"multi-slot tab-hooks home only)"
        )
