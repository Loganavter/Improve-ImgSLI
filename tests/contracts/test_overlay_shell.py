"""Overlay-shell ownership + ctx-first intake (overlay-shell S1).

Pins the S1 seam between the shared engine overlay shell
(``src/engine/overlay/``) and the pilot tab passes:

* engine owns GPU: the three pilot ``passes.py`` (guides / divider /
  capture) declare bindings only -- no GPU allocation, no bespoke
  pipeline builders, no draw-recorder calls, no retained pipeline /
  texture / buffer attributes of their own. ``initialize`` mounts the
  shell, ``release`` tears it down, ``record`` draws through it.
* ctx-first model intake: the engine takes engine types + the opaque
  ``ctx`` and never tab geometry -- ``src/engine/overlay/`` names no
  tab/plugin module, no ``widget``, and its resolver protocol takes
  ``ctx`` first and returns packed ``tuple[bytes, ...]`` blocks.
* naming fence: ``OverlayShell`` / ``UniformPassView`` deliberately do
  NOT reuse the legacy tab-side resource shape (``initialize`` /
  ``ensure_items`` / ``release`` + ``uniform_buffers`` / ``srbs``) whose
  single-owner dogma still points at the tab-side class until the
  remaining consumers migrate. Do not rename this shell back onto the
  legacy names while both exist; when the legacy class retires,
  re-point that dogma here instead.

S1 owns this file; S2 (MC mount) extends it only: add MC pass paths to
``_PILOT_PASSES`` (renaming the constant is allowed but keep both tabs
in one list) and extend the stem/size map. Ownership and intake rules
apply unchanged to every added pass.

R3a (textured shell) extends it further: the ``R3A TEXTURED`` section
below pins the ``TexturedOverlayShell`` seam (``src/engine/overlay/``)
and the first raster mount (IC drag overlay). It also widens two S1
shape tests to the new module (``test_overlay_package_shape`` file
list, legacy-fingerprint loop) -- the only S1 edits R3a makes.
"""

from __future__ import annotations

import ast
import re

from ._framework import ROOT, parse, read

OVERLAY = ROOT / "src" / "engine" / "overlay"

# Pilot scope (S1) + first mounted MC pass (R-a). S2 extends with MC pass paths; rules below apply
# unchanged to every listed file.
_PILOT_PASSES = {
    "src/tabs/image_compare/canvas/features/guides/passes.py": (
        "guides",
        128,
    ),
    "src/tabs/image_compare/canvas/features/divider/passes.py": (
        "divider",
        128,
    ),
    "src/tabs/image_compare/canvas/features/capture/passes.py": (
        "capture",
        112,
    ),
    "src/tabs/multi_compare/canvas/features/grid_dividers/passes.py": (
        "grid_divider",
        96,
    ),
}

# GPU allocation the engine owns -- never spelled in a tab pass.
_FORBIDDEN_ALLOC = (
    "newGraphicsPipeline",
    "newBuffer",
    "newTexture",
    "newTextureArray",
    "newSampler",
    "newShaderResourceBindings",
)

# Draw-recorder calls the engine owns -- tab record() reaches them only
# through ``self._shell.draw(...)`` (pinned separately below).
_FORBIDDEN_RECORD = (
    "command_buffer.set",
    "command_buffer.draw",
)

# Bespoke pipeline builders retired with the divider hand-rolled shell.
_FORBIDDEN_BUILDERS = (
    "def _ensure_pipeline",
    "def _build_srb",
)

# Retained GPU attributes the engine owns (``self.<name>`` ownership in
# a tab pass). ``self.resources`` (compat view) and ``self._shell``
# (engine shell) are the only resource holders allowed.
_FORBIDDEN_SELF_GPU_RE = re.compile(
    r"self\.(pipeline|srb|srbs|texture|uniform_buffer|uniform_buffers|vertex_buffer)\b"
)


def _parse(path):
    tree = parse(path)
    if tree is None:
        raise SyntaxError(f"cannot parse {path}")
    return tree


def _methods(tree: ast.Module, class_name: str) -> dict[str, ast.FunctionDef]:
    out: dict[str, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[stmt.name] = stmt
    return out


def _unparse(node) -> str:
    try:
        return ast.unparse(node).strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Engine owns GPU: tab passes declare bindings only
# ---------------------------------------------------------------------------


def test_pilot_passes_allocate_no_gpu_objects():
    offenders: list[str] = []
    for rel_path in _PILOT_PASSES:
        text = read(ROOT / rel_path)
        for mark in _FORBIDDEN_ALLOC:
            if mark in text:
                offenders.append(
                    f"{rel_path} spells '{mark}' -- GPU allocation "
                    f"lives in engine.overlay.OverlayShell"
                )
        for mark in _FORBIDDEN_BUILDERS:
            if mark in text:
                offenders.append(
                    f"{rel_path} defines '{mark}' -- pipeline building "
                    f"lives in engine.overlay.OverlayShell"
                )
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN_SELF_GPU_RE.search(line):
                offenders.append(
                    f"{rel_path}:{lineno} owns a GPU attribute "
                    f"({line.strip()[:80]!r}) -- passes hold "
                    f"self._shell / self.resources only"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_pilot_passes_record_only_through_shell_draw():
    offenders: list[str] = []
    for rel_path in _PILOT_PASSES:
        tree = _parse(ROOT / rel_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Pass"):
                continue
            methods = _methods(tree, node.name)
            record = methods.get("record")
            if record is None:
                offenders.append(f"{rel_path}: {node.name} defines no record()")
                continue
            body = _unparse(record)
            for mark in _FORBIDDEN_RECORD:
                if mark in body:
                    offenders.append(
                        f"{rel_path}: {node.name}.record calls '{mark}' -- "
                        f"draw-recorder calls live in OverlayShell.draw; "
                        f"tab record() delegates via self._shell.draw(...)"
                    )
            if "self._shell.draw" not in body:
                offenders.append(
                    f"{rel_path}: {node.name}.record never calls "
                    f"self._shell.draw -- the engine owns the draw"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_pilot_passes_mount_and_teardown_shell():
    offenders: list[str] = []
    for rel_path in _PILOT_PASSES:
        tree = _parse(ROOT / rel_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Pass"):
                continue
            methods = _methods(tree, node.name)
            init = methods.get("initialize")
            release = methods.get("release")
            if init is None or "self._shell.mount" not in _unparse(init):
                offenders.append(
                    f"{rel_path}: {node.name}.initialize must mount the "
                    f"engine shell (self._shell.mount(...)) -- no bespoke init"
                )
            if release is None or "self._shell.teardown" not in _unparse(release):
                offenders.append(
                    f"{rel_path}: {node.name}.release must tear down the "
                    f"engine shell (self._shell.teardown())"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_pilot_passes_declare_bindings():
    offenders: list[str] = []
    for rel_path, (stem, size) in _PILOT_PASSES.items():
        text = read(ROOT / rel_path)
        tree = _parse(ROOT / rel_path)
        if "from engine.overlay import" not in text and (
            "from engine.overlay" not in text
        ):
            offenders.append(
                f"{rel_path} never imports engine.overlay -- passes "
                f"declare bindings against the shared shell"
            )
        if "OverlayBinding(" not in text or f'shader_stem="{stem}"' not in text:
            offenders.append(
                f"{rel_path} defines no OverlayBinding(shader_stem={stem!r})"
            )
        if f"uniform_size={size}" not in text.replace(" ", "").replace(
            "_UNIFORM_SIZE", str(size)
        ) and str(size) not in text and not any(
            sym in text
            for sym in (
                "DIVIDER_UNIFORM_SIZE",
                "GUIDES_UNIFORM_SIZE",
                "CAPTURE_UNIFORM_SIZE",
                "GRID_DIVIDER_UNIFORM_SIZE",
            )
        ):
            offenders.append(f"{rel_path} declares no uniform_size={size}")
        if "OverlayResolver" not in text and "SemanticResolver" not in text:
            offenders.append(
                f"{rel_path} never names OverlayResolver -- per-frame "
                f"blocks flow through the ctx-first resolver"
            )
        resolvers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "resolve"
        ]
        if not resolvers:
            offenders.append(
                f"{rel_path} defines no ctx-first resolve() block resolver"
            )
        for func in resolvers:
            args = [a.arg for a in func.args.args]
            if not args or args[0] != "ctx":
                offenders.append(
                    f"{rel_path}:{func.lineno} resolve{tuple(args)} -- "
                    f"resolvers take the frame context first"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


# ---------------------------------------------------------------------------
# Ctx-first intake: engine takes engine types + opaque ctx, never tab geometry
# ---------------------------------------------------------------------------


def test_overlay_package_shape():
    files = sorted(
        p.name for p in OVERLAY.glob("*.py") if "__pycache__" not in p.parts
    )
    assert files == [
        "__init__.py",
        "bindings.py",
        "semantic.py",
        "shell.py",
        "textured.py",
        "views.py",
    ], f"src/engine/overlay/ holds the shells + seams only: {files}"


def test_overlay_names_no_tab_geometry():
    leaks: list[str] = []
    app_res = [
        re.compile(r"tabs\.[A-Za-z_]"),
        re.compile(r"plugins\.[A-Za-z_]"),
        re.compile(r"src/tabs"),
        re.compile(r"src/plugins"),
    ]
    for py in sorted(OVERLAY.glob("*.py")):
        if "__pycache__" in py.parts:
            continue
        text = read(py)
        for rx in app_res:
            if rx.search(text):
                leaks.append(
                    f"src/engine/overlay/{py.name} references app layer "
                    f"({rx.pattern!r}) -- the engine never names its callers"
                )
        tree = parse(py)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if (node.level or 0) > 0:
                    continue  # intra-package relative import (bindings/shell/views)
                top = node.module.split(".")[0]
                assert top in ("__future__", "dataclasses", "pathlib", "typing", "engine", "PySide6"), (
                    f"src/engine/overlay/{py.name}:{node.lineno} imports "
                    f"'{node.module}' -- engine overlay imports stdlib, "
                    f"Qt, and engine modules only"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in (
                        "struct",
                        "pathlib",
                        "typing",
                        "PySide6",
                    ), (
                        f"src/engine/overlay/{py.name}:{node.lineno} imports "
                        f"'{alias.name}' -- stdlib/Qt only"
                    )
        # No ``widget`` anywhere: viewport/scissor arrive precomputed, the
        # frame context arrives opaque. (Text scan: comments count too --
        # describe callers as "the tab", never by handle name.)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "widget" in line.lower():
                leaks.append(
                    f"src/engine/overlay/{py.name}:{lineno} names 'widget' "
                    f"({line.strip()[:80]!r}) -- the shell takes "
                    f"precomputed sizes/scissors, never host handles"
                )
    assert not leaks, "\n  - " + "\n  - ".join(leaks)


def test_overlay_shell_entry_points():
    tree = _parse(OVERLAY / "shell.py")
    methods = _methods(tree, "OverlayShell")
    for entry in (
        "mount",
        "ensure_slots",
        "stage_quad",
        "stage_slot",
        "clip_matrix",
        "draw",
        "teardown",
    ):
        assert entry in methods, (
            f"OverlayShell.{entry} missing -- S2 mounts onto these names; "
            f"renaming breaks the handoff"
        )
    assert "__init__" in methods
    init = methods["__init__"]
    assert [a.arg for a in init.args.args] == ["self", "uniform_size"], (
        "OverlayShell takes its uniform size at construction (bindings declare it)"
    )


def test_overlay_resolver_protocol_is_ctx_first():
    tree = _parse(OVERLAY / "bindings.py")
    classes = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    assert "OverlayResolver" in classes, "bindings.py must declare OverlayResolver"
    assert "OverlayBinding" in classes, "bindings.py must declare OverlayBinding"
    resolver = classes["OverlayResolver"]
    assert any(
        isinstance(b, ast.Name) and b.id == "Protocol"
        or isinstance(b, ast.Subscript)
        and getattr(getattr(b, "value", None), "id", "") == "Protocol"
        for b in resolver.bases
    ) or "Protocol" in _unparse(resolver), (
        "OverlayResolver must be a typing.Protocol (structural seam)"
    )
    call = _methods(tree, "OverlayResolver").get("__call__")
    assert call is not None, "OverlayResolver must declare __call__"
    assert [a.arg for a in call.args.args][:2] == ["self", "ctx"], (
        "OverlayResolver.__call__ takes ctx first (engine types + opaque ctx)"
    )
    assert "tuple[bytes, ...]" in _unparse(call.returns), (
        "OverlayResolver returns packed tuple[bytes, ...] blocks"
    )
    binding = _methods(tree, "OverlayBinding")
    assert not binding, "OverlayBinding is a dataclass bundle, not a method bag"


# ---------------------------------------------------------------------------
# MC scope (S2): model-side migrate + texture-raster pins.
#
# S2 extends this S1-owned file only: the lists and tests below. S1 code
# above is untouched. MC scene sources (``scene/passes/*``) are NOT
# CanvasRenderPasses -- they own no GPU objects and define no
# initialize/record/release -- so the pilot mount/record dogmas cannot apply
# to them verbatim. Per-pass verdicts (ruling 2, proven here, not asserted):
#
# * dividers.py -> MIGRATED (model side + R-a mount): pure geometry
#   (composition gaps -> fb rects + color) exposing a ctx-first
#   ``resolve(ctx)`` returning engine types (``tuple[bytes, ...]``), now
#   consumed by the mounted ``GridDividersPass`` (R-a): that pass joined
#   ``_PILOT_PASSES`` above, so the mount/record/binding dogmas prove the
#   shared shell path, and ``test_mc_grid_dividers_shell_shape_matches...``
#   pins the quad shape on the shell plus the tab's binding. The retired
#   ``test_mc_grid_dividers_shell_still_hand_rolled`` tripwire used to flag
#   the outstanding mount here.
# * labels.py / drag_overlay.py -> PIN (genuinely pass-owned): glyph and
#   interaction raster needs a framebuffer-sized texture upload
#   (``uploadTexture`` + sampler in the shared texture base), which the
#   uniform-only ``OverlayShell`` cannot host (no texture/sampler entry
#   points). Drag additionally takes live host handles (``host.state`` /
#   ``host._translate``), not an opaque ctx. Pinned here as what stays + why.
#
# R3b supersedes the labels/drag PIN above without touching S1: the
# textured engine shell (``engine.overlay.textured``, R3a) now hosts
# exactly that texture-upload shape, so all three MC raster mounts
# (labels / drag / focus_dim) ride ``TexturedOverlayShell`` directly
# (``_TEXTURED_PASSES`` + the R3B section below) and both tab-side
# mirrors retire atomically. Scene sources (``scene/passes/*``) stay
# S2-pinned read-only; per-pass DPR behavior is preserved, never unified.
# ---------------------------------------------------------------------------

# Model-side migrate source: must expose the ctx-first resolver intake.
_MC_MIGRATE_SOURCE = "src/tabs/multi_compare/scene/passes/dividers.py"

# Raster pins: scene source -> GPU shell consuming it (shell files are
# READ ONLY for S2; asserted here, never edited).
_MC_TEXTURE_PINS = {
    "src/tabs/multi_compare/scene/passes/labels.py": (
        "src/tabs/multi_compare/canvas/features/layer_labels/passes.py"
    ),
    "src/tabs/multi_compare/scene/passes/drag_overlay.py": (
        "src/tabs/multi_compare/canvas/features/drag_drop_overlay/passes.py"
    ),
}

# Shared texture-raster base both pinned shells subclass (read-only for S2).
_MC_TEXTURE_BASE = "src/tabs/multi_compare/canvas/rhi_overlay_pass_base.py"

# Hand-rolled quad shell whose S6 mount consumes _MC_MIGRATE_SOURCE.resolve
# (read-only for S2; shape proven shared, mount outstanding).
_MC_QUAD_SHELL = (
    "src/tabs/multi_compare/canvas/features/grid_dividers/passes.py"
)

_MC_MODEL_SOURCES = (_MC_MIGRATE_SOURCE, *_MC_TEXTURE_PINS)


def _module_funcs(tree: ast.Module, name: str) -> list:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]


def test_mc_model_sources_own_no_gpu_objects():
    """MC scene sources are pure CPU geometry/raster: no GPU spelling."""
    offenders: list[str] = []
    for rel_path in _MC_MODEL_SOURCES:
        text = read(ROOT / rel_path)
        for mark in _FORBIDDEN_ALLOC + _FORBIDDEN_BUILDERS:
            if mark in text:
                offenders.append(
                    f"{rel_path} spells '{mark}' -- scene sources own "
                    f"no GPU objects (S2 migrate/pin surface)"
                )
        if "QRhi" in text:
            offenders.append(
                f"{rel_path} names 'QRhi' -- scene sources stay CPU-side "
                f"(QPainter/QImage geometry only)"
            )
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN_SELF_GPU_RE.search(line):
                offenders.append(
                    f"{rel_path}:{lineno} owns a GPU attribute "
                    f"({line.strip()[:80]!r})"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_mc_dividers_exposes_ctx_first_resolver():
    """Migrate intake: dividers.py exposes resolve(ctx) -> tuple[bytes, ...]."""
    tree = _parse(ROOT / _MC_MIGRATE_SOURCE)
    resolvers = _module_funcs(tree, "resolve")
    assert len(resolvers) == 1, (
        f"{_MC_MIGRATE_SOURCE} must define exactly one module-level "
        f"resolve() (the S6 shell seam), found {len(resolvers)}"
    )
    func = resolvers[0]
    assert [a.arg for a in func.args.args] == ["ctx"], (
        f"{_MC_MIGRATE_SOURCE}: resolve{tuple(a.arg for a in func.args.args)} -- "
        f"resolvers take the frame context first (engine types + opaque ctx)"
    )
    assert "tuple[bytes, ...]" in _unparse(func.returns), (
        f"{_MC_MIGRATE_SOURCE}: resolve must return packed tuple[bytes, ...]"
    )
    text = read(ROOT / _MC_MIGRATE_SOURCE)
    assert "_DIVIDER_BLOCK_FMT" in text, (
        f"{_MC_MIGRATE_SOURCE} must declare its block layout for the S6 shell"
    )


def test_mc_raster_sources_expose_no_resolver():
    """Pin discriminator: raster sources stay QPainter-based, no resolve()."""
    offenders: list[str] = []
    for rel_path in _MC_TEXTURE_PINS:
        tree = _parse(ROOT / rel_path)
        found = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "resolve"
        ]
        if found:
            offenders.append(
                f"{rel_path} defines resolve() -- raster pins keep "
                f"QPainter intake; only the dividers migrate source "
                f"exposes the bytes seam"
            )
        text = read(ROOT / rel_path)
        if "QPainter" not in text:
            offenders.append(
                f"{rel_path} never names QPainter -- raster pins stay "
                f"CPU-raster sources by definition"
            )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_mc_raster_mounts_ride_textured_engine_shell():
    """Mount proof (R3b): the glyph/interaction raster passes ride the
    engine textured shell -- the pin reason moved with them.

    R3b retires the tab-side texture-upload path (both
    ``rhi_overlay_pass_base`` mirrors are gone, pinned below): the
    ``uploadTexture`` + ``sampledTexture`` path the S2 pin cited now
    lives in ``engine.overlay.textured`` only, and every MC raster
    mount declares its binding against it (proven per-pass by the
    ``test_textured_*`` dogmas over ``_TEXTURED_PASSES`` above).
    """
    engine_text = read(OVERLAY / "textured.py")
    for marker in ("uploadTexture", "sampledTexture"):
        assert marker in engine_text, (
            f"src/engine/overlay/textured.py lost '{marker}' -- it is the "
            f"pin reason the MC raster mounts render through"
        )
    for mirror_rel in _RETIRED_TEXTURED_MIRRORS:
        tree = _parse(ROOT / mirror_rel)
        for node in ast.walk(tree):
            assert not (
                isinstance(node, ast.ClassDef)
                and node.name == "FullscreenOverlayTexturePass"
            ), (
                f"{mirror_rel} redefines FullscreenOverlayTexturePass -- "
                f"the mirror retired in R3b; the engine shell owns the "
                f"textured shape now"
            )


def test_no_tab_side_textured_mirror_classes():
    """Retire pin (R3b, ruling 3): no tab-side textured defs remain.

    ``FullscreenOverlayTexturePass`` is defined nowhere under
    ``src/tabs`` -- the last subclasses (3 MC passes + IC drag) all
    mount ``engine.overlay.TexturedOverlayShell`` directly. Docstring
    mentions (e.g. registry prose) are documentation, not defs, and
    stay allowed; only the class definition is pinned here.
    """
    offenders: list[str] = []
    for rel_path in (
        "src/tabs/image_compare/canvas/features/drag_drop_overlay/passes.py",
        "src/tabs/multi_compare/canvas/features/layer_labels/passes.py",
        "src/tabs/multi_compare/canvas/features/drag_drop_overlay/passes.py",
        "src/tabs/multi_compare/canvas/features/focus_dim/passes.py",
        *_RETIRED_TEXTURED_MIRRORS,
    ):
        tree = _parse(ROOT / rel_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and (
                node.name == "FullscreenOverlayTexturePass"
                or any(
                    _unparse(base) == "FullscreenOverlayTexturePass"
                    for base in node.bases
                )
            ):
                offenders.append(
                    f"{rel_path}:{node.lineno} class {node.name} still "
                    f"owns/subclasses the retired mirror -- mounts subclass "
                    f"CanvasRenderPass directly"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_mc_drag_intake_stays_host_bound():
    """Pin reason (drag): live host handles no opaque ctx can carry."""
    text = read(ROOT / "src/tabs/multi_compare/scene/passes/drag_overlay.py")
    for marker in ("host.state", "host._translate"):
        assert marker in text, (
            "src/tabs/multi_compare/scene/passes/drag_overlay.py must keep "
            f"'{marker}' -- live drag state/translations live on host "
            f"handles, so this source cannot take ctx-first bytes intake"
        )


def test_mc_grid_dividers_shell_shape_matches_shared_quad():
    """Mount proof (dividers): GridDividersPass rides the shared uniform
    quad shell, so the pipeline shape lives in ``engine.overlay`` and the
    tab only declares its binding. Pins both halves: the shell keeps the
    quad shape (TriangleStrip, SrcAlpha blend, 2xFloat2 layout) and the
    mounted pass sits under the pilot dogmas with its grid_divider stem
    and 96-byte blocks."""
    assert _MC_QUAD_SHELL in _PILOT_PASSES, (
        f"{_MC_QUAD_SHELL} must stay mounted under the pilot ownership "
        f"dogmas ({sorted(_PILOT_PASSES)}) -- the engine owns the draw"
    )
    assert _PILOT_PASSES[_MC_QUAD_SHELL] == ("grid_divider", 96), (
        f"{_MC_QUAD_SHELL} binding drifted: {_PILOT_PASSES[_MC_QUAD_SHELL]} -- "
        f"the mount declares shader_stem='grid_divider', uniform_size=96"
    )
    shell_text = read(ROOT / "src" / "engine" / "overlay" / "shell.py")
    for marker in (
        "TriangleStrip",
        "BlendFactor.SrcAlpha",
        "BlendFactor.OneMinusSrcAlpha",
        "Format.Float2",
    ):
        assert marker in shell_text, (
            "src/engine/overlay/shell.py lost "
            f"'{marker}' -- the mounted dividers render through the "
            f"shared-quad pipeline shape"
        )


def test_overlay_shell_avoids_legacy_resource_fingerprint():
    """The shared shell must not re-trigger the legacy dogma by accident.

    ``test_canvas_fullscreen_pass_resources_single_owner`` fingerprints
    the legacy shape (``initialize``/``ensure_items``/``release`` +
    ``uniform_buffers``/``srbs``). The names below are the fence: while
    the legacy tab-side class still owns that dogma, this shell keeps
    its renamed entry points. If this test fails, do not "fix" it by
    renaming back -- retire the legacy class and re-point that dogma
    here instead.
    """
    legacy_methods = {"initialize", "ensure_items", "release"}
    legacy_attrs = {"uniform_buffers", "srbs"}
    for name in ("shell.py", "textured.py", "views.py"):
        tree = _parse(OVERLAY / name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            method_names = {
                stmt.name
                for stmt in node.body
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
            self_attrs = {
                sub.attr
                for sub in ast.walk(node)
                if isinstance(sub, ast.Attribute)
                and isinstance(sub.value, ast.Name)
                and sub.value.id == "self"
            }
            assert not (
                legacy_methods.issubset(method_names)
                and legacy_attrs.issubset(self_attrs)
            ), (
                f"src/engine/overlay/{name} class {node.name} matches the "
                f"legacy duplicate-resource fingerprint -- keep the "
                f"renamed shell API while the legacy owner stands"
            )


# ---------------------------------------------------------------------------
# R3A TEXTURED (R3a owns this section; R3b extends it with MC mounts).
#
# Pins the ``TexturedOverlayShell`` seam (``src/engine/overlay/``)
# and the first raster mount (IC drag overlay):
#
# * engine owns GPU: the mounted ``passes.py`` declares its binding
#   only -- no GPU allocation, no bespoke pipeline builders, no
#   draw-recorder calls, no retained pipeline / texture / buffer
#   attributes of its own. ``initialize`` mounts the shell,
#   ``release`` tears it down, ``record`` draws through it.
# * bytes intake: the engine takes ``(width, height, pixels)`` bytes
#   + the opaque ``ctx`` and never host images -- ``textured.py``
#   names no tab/plugin module, no ``widget``, no ``QImage``-typed
#   intake; its resolver protocol takes ``ctx`` first and returns
#   ``tuple[int, int, bytes] | None``.
# * R0 shape: uploadTexture + Linear/Linear/None ClampToEdge sampler
#   + premultiplied One/OneMinusSrcAlpha blend + TriangleStrip, no
#   scissor; mount builds vertex buffer + 64B uniform + sampler +
#   1x1 RGBA8 placeholder + SRB + pipeline; prepare stages quad +
#   clip, resizes (destroy texture, new RGBA8 texture, rebuild SRB,
#   force-rebuild pipeline), uploads, sets active; record draws one
#   fullscreen quad over the full framebuffer.
# ---------------------------------------------------------------------------

# Raster mounts on the textured shell: pass path -> shader stem.
# R3b: all three MC raster passes join the IC drag mount here.
_TEXTURED_PASSES = {
    "src/tabs/image_compare/canvas/features/drag_drop_overlay/passes.py": ("overlay",),
    "src/tabs/multi_compare/canvas/features/layer_labels/passes.py": ("overlay",),
    "src/tabs/multi_compare/canvas/features/drag_drop_overlay/passes.py": ("overlay",),
    "src/tabs/multi_compare/canvas/features/focus_dim/passes.py": ("overlay",),
}

# Tab-side textured mirrors retired by R3b (ruling 3, atomic with the
# last MC mount): both files keep their module shells, neither may
# define the mirror class again -- the engine shell is the single owner.
_RETIRED_TEXTURED_MIRRORS = (
    "src/tabs/image_compare/canvas/rhi_overlay_pass_base.py",
    "src/tabs/multi_compare/canvas/rhi_overlay_pass_base.py",
)


def test_textured_passes_allocate_no_gpu_objects():
    offenders: list[str] = []
    for rel_path in _TEXTURED_PASSES:
        text = read(ROOT / rel_path)
        for mark in _FORBIDDEN_ALLOC:
            if mark in text:
                offenders.append(
                    f"{rel_path} spells '{mark}' -- GPU allocation "
                    f"lives in engine.overlay.TexturedOverlayShell"
                )
        for mark in _FORBIDDEN_BUILDERS:
            if mark in text:
                offenders.append(
                    f"{rel_path} defines '{mark}' -- pipeline building "
                    f"lives in engine.overlay.TexturedOverlayShell"
                )
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN_SELF_GPU_RE.search(line):
                offenders.append(
                    f"{rel_path}:{lineno} owns a GPU attribute "
                    f"({line.strip()[:80]!r}) -- passes hold "
                    f"self._shell only"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_textured_passes_record_only_through_shell_draw():
    offenders: list[str] = []
    for rel_path in _TEXTURED_PASSES:
        tree = _parse(ROOT / rel_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Pass"):
                continue
            methods = _methods(tree, node.name)
            record = methods.get("record")
            if record is None:
                offenders.append(f"{rel_path}: {node.name} defines no record()")
                continue
            body = _unparse(record)
            for mark in _FORBIDDEN_RECORD:
                if mark in body:
                    offenders.append(
                        f"{rel_path}: {node.name}.record calls '{mark}' -- "
                        f"draw-recorder calls live in "
                        f"TexturedOverlayShell.draw; tab record() "
                        f"delegates via self._shell.draw(...)"
                    )
            if "self._shell.draw" not in body:
                offenders.append(
                    f"{rel_path}: {node.name}.record never calls "
                    f"self._shell.draw -- the engine owns the draw"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_textured_passes_mount_and_teardown_shell():
    offenders: list[str] = []
    for rel_path in _TEXTURED_PASSES:
        tree = _parse(ROOT / rel_path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Pass"):
                continue
            methods = _methods(tree, node.name)
            init = methods.get("initialize")
            release = methods.get("release")
            if init is None or "self._shell.mount" not in _unparse(init):
                offenders.append(
                    f"{rel_path}: {node.name}.initialize must mount the "
                    f"engine shell (self._shell.mount(...)) -- no bespoke init"
                )
            if release is None or "self._shell.teardown" not in _unparse(release):
                offenders.append(
                    f"{rel_path}: {node.name}.release must tear down the "
                    f"engine shell (self._shell.teardown())"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_textured_passes_declare_bindings():
    offenders: list[str] = []
    for rel_path, (stem,) in _TEXTURED_PASSES.items():
        text = read(ROOT / rel_path)
        tree = _parse(ROOT / rel_path)
        if "from engine.overlay import" not in text and (
            "from engine.overlay" not in text
        ):
            offenders.append(
                f"{rel_path} never imports engine.overlay -- passes "
                f"declare bindings against the shared shell"
            )
        if "TexturedOverlayBinding(" not in text or f'shader_stem="{stem}"' not in text:
            offenders.append(
                f"{rel_path} defines no TexturedOverlayBinding(shader_stem={stem!r})"
            )
        if "TexturedOverlayResolver" not in text:
            offenders.append(
                f"{rel_path} never names TexturedOverlayResolver -- per-frame "
                f"rasters flow through the ctx-first resolver"
            )
        resolvers = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "resolve"
        ]
        if not resolvers:
            offenders.append(
                f"{rel_path} defines no ctx-first resolve() raster resolver"
            )
        for func in resolvers:
            args = [a.arg for a in func.args.args]
            if not args or args[0] != "ctx":
                offenders.append(
                    f"{rel_path}:{func.lineno} resolve{tuple(args)} -- "
                    f"resolvers take the frame context first"
                )
            if "tuple[int, int, bytes] | None" not in _unparse(func).replace(
                "Optional", ""
            ) and "tuple[int, int, bytes]" not in _unparse(func.returns):
                offenders.append(
                    f"{rel_path}:{func.lineno} resolve must return "
                    f"tuple[int, int, bytes] | None (framebuffer bytes intake)"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_textured_shell_entry_points():
    tree = _parse(OVERLAY / "textured.py")
    methods = _methods(tree, "TexturedOverlayShell")
    for entry in (
        "mount",
        "stage_quad",
        "stage_clip",
        "upload_frame",
        "draw",
        "teardown",
    ):
        assert entry in methods, (
            f"TexturedOverlayShell.{entry} missing -- R3b mounts onto "
            f"these names; renaming breaks the handoff"
        )
    assert "__init__" in methods
    text = read(OVERLAY / "textured.py")
    assert "TEXTURED_UNIFORM_SIZE = 64" in text, (
        "textured.py must pin TEXTURED_UNIFORM_SIZE = 64 -- the 64B "
        "clip-matrix uniform the overlay shaders read"
    )


def test_textured_resolver_protocol_is_ctx_first():
    tree = _parse(OVERLAY / "textured.py")
    classes = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    assert "TexturedOverlayResolver" in classes, (
        "textured.py must declare TexturedOverlayResolver"
    )
    assert "TexturedOverlayBinding" in classes, (
        "textured.py must declare TexturedOverlayBinding"
    )
    resolver = classes["TexturedOverlayResolver"]
    assert any(
        isinstance(b, ast.Name)
        and b.id == "Protocol"
        or isinstance(b, ast.Subscript)
        and getattr(getattr(b, "value", None), "id", "") == "Protocol"
        for b in resolver.bases
    ) or "Protocol" in _unparse(resolver), (
        "TexturedOverlayResolver must be a typing.Protocol (structural seam)"
    )
    call = _methods(tree, "TexturedOverlayResolver").get("__call__")
    assert call is not None, "TexturedOverlayResolver must declare __call__"
    assert [a.arg for a in call.args.args][:2] == ["self", "ctx"], (
        "TexturedOverlayResolver.__call__ takes ctx first (bytes + opaque ctx)"
    )
    assert "tuple[int, int, bytes] | None" in _unparse(call), (
        "TexturedOverlayResolver returns (width, height, pixels) bytes or None"
    )
    binding = _methods(tree, "TexturedOverlayBinding")
    assert not binding, "TexturedOverlayBinding is a dataclass bundle, not a method bag"


def test_textured_shell_keeps_r0_pipeline_shape():
    """R0 shape: premul blend + linear sampler + TriangleStrip, no scissor."""
    text = read(OVERLAY / "textured.py")
    for marker in (
        "uploadTexture",
        "sampledTexture",
        "Filter.Linear",
        "AddressMode.ClampToEdge",
        "BlendFactor.One",
        "BlendFactor.OneMinusSrcAlpha",
        "Topology.TriangleStrip",
        "Format.RGBA8",
        "Format.Float2",
        "FULLSCREEN_VERTICES",
    ):
        assert marker in text, (
            f"src/engine/overlay/textured.py lost '{marker}' -- the "
            f"mounted raster passes render through this pipeline shape"
        )
    assert "UsesScissor" not in text, (
        "src/engine/overlay/textured.py gained a scissor flag -- the "
        "textured shell draws one fullscreen quad with no scissor (R0)"
    )
    assert "TEXTURED_UNIFORM_SIZE" in text and "64" in text


def test_textured_shell_mount_builds_full_set():
    """Mount builds vertex + 64B uniform + sampler + 1x1 + SRB + pipeline."""
    tree = _parse(OVERLAY / "textured.py")
    mount = _methods(tree, "TexturedOverlayShell").get("mount")
    assert mount is not None, "TexturedOverlayShell.mount missing"
    body = _unparse(mount)
    for mark in (
        "newBuffer",
        "newSampler",
        "newTexture",
        "newShaderResourceBindings",
        "_ensure_pipeline",
        "_build_srb",
    ):
        assert mark in body or mark in _unparse(tree), (
            f"TexturedOverlayShell.mount never reaches '{mark}' -- mount "
            f"builds the full retained set (R0)"
        )
    upload = _methods(tree, "TexturedOverlayShell").get("upload_frame")
    assert upload is not None, "TexturedOverlayShell.upload_frame missing"
    upload_body = _unparse(upload)
    for mark in ("newTexture", "_build_srb", "_ensure_pipeline", "uploadTexture"):
        assert mark in upload_body, (
            f"TexturedOverlayShell.upload_frame never reaches '{mark}' -- "
            f"the resize path (destroy texture, new RGBA8 texture, rebuild "
            f"SRB, force-rebuild pipeline) + upload live here (R0)"
        )


def test_ic_drag_mount_rides_engine_shell_directly():
    """IC drag owns no mirror base: engine shell, kept seams, strict draw."""
    rel_path = "src/tabs/image_compare/canvas/features/drag_drop_overlay/passes.py"
    tree = _parse(ROOT / rel_path)
    text = read(ROOT / rel_path)
    assert "FullscreenOverlayTexturePass" not in text, (
        f"{rel_path} still names the retired mirror base -- R3a mounts "
        f"the engine shell directly (R3b deletes the mirror)"
    )
    pass_nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name.endswith("Pass")
    ]
    assert pass_nodes, f"{rel_path} defines no *Pass"
    for node in pass_nodes:
        bases = [_unparse(base) for base in node.bases]
        assert bases == ["CanvasRenderPass"], (
            f"{rel_path}: {node.name} bases {bases} -- the mount subclasses "
            f"the pass contract directly, never the retired mirror"
        )
    # Kept tab-side seams: gating, stacking, raster cache keys.
    for marker in ("should_paint", "stack_role", "_raster", "_drag_overlay_cache_key"):
        assert marker in text, (
            f"{rel_path} lost '{marker}' -- gating/stacking/raster-cache "
            f"stay tab-side on the mount"
        )
    assert "RENDER_PASSES" in text, f"{rel_path} must keep RENDER_PASSES"


# ---------------------------------------------------------------------------
# R3B TEXTURED-MC (R3b owns this section).
#
# All three MC raster passes mount TexturedOverlayShell directly (same
# seam as the R3a IC drag mount): engine owns GPU, ctx-first bytes
# intake, shader_stem='overlay'. Per-pass DPR behavior is preserved,
# never unified (labels source-owned, drag scales, focus is DPR-free
# rect fill). The tab-side mirrors retire in the same wave (ruling 3,
# atomic): pinned absent by test_no_tab_side_textured_mirror_classes.
# ---------------------------------------------------------------------------

# MC mount -> tab-side seams that must stay on the mount (gating,
# stacking, raster behavior owned by the pass, not the shell).
_MC_TEXTURED_SEAMS = {
    "src/tabs/multi_compare/canvas/features/layer_labels/passes.py": (
        "should_paint",
        "stack_role",
        "_raster",
        "LabelsOverlaySource",
        "RENDER_PASSES",
    ),
    "src/tabs/multi_compare/canvas/features/drag_drop_overlay/passes.py": (
        "should_paint",
        "stack_role",
        "_raster",
        "DragDropOverlaySource",
        "_dbg_recorded",
        "RENDER_PASSES",
    ),
    "src/tabs/multi_compare/canvas/features/focus_dim/passes.py": (
        "should_paint",
        "stack_role",
        "_raster",
        "DIM_COLOR",
        "RENDER_PASSES",
    ),
}


def test_mc_textured_mounts_ride_engine_shell_directly():
    """MC mounts own no mirror base: engine shell, kept seams, strict draw."""
    offenders: list[str] = []
    for rel_path, seams in _MC_TEXTURED_SEAMS.items():
        tree = _parse(ROOT / rel_path)
        text = read(ROOT / rel_path)
        if "FullscreenOverlayTexturePass" in text:
            offenders.append(
                f"{rel_path} still names the retired mirror base -- R3b mounts "
                f"the engine shell directly"
            )
        pass_nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name.endswith("Pass")
        ]
        if not pass_nodes:
            offenders.append(f"{rel_path} defines no *Pass")
        for node in pass_nodes:
            bases = [_unparse(base) for base in node.bases]
            if bases != ["CanvasRenderPass"]:
                offenders.append(
                    f"{rel_path}: {node.name} bases {bases} -- the mount subclasses "
                    f"the pass contract directly, never the retired mirror"
                )
        for marker in seams:
            if marker not in text:
                offenders.append(
                    f"{rel_path} lost '{marker}' -- gating/stacking/raster seams "
                    f"stay tab-side on the mount"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


# ---------------------------------------------------------------------------
# R3B DEDUP (behavior pin): an unchanged frame is not re-uploaded.
#
# MC raster passes (labels / drag / focus-dim) call ``upload_frame`` every
# rendered frame while their gate stays active. The shell remembers the
# last uploaded frame's content signature and skips the (fullscreen)
# ``uploadTexture`` when the bytes repeat with an unchanged texture size.
# Behavior, not shape: a fake resource-update batch counts uploads.
# ---------------------------------------------------------------------------


class _CountingUpdates:
    def __init__(self) -> None:
        self.uploads: list = []

    def uploadTexture(self, texture, image) -> None:
        self.uploads.append((texture, image))


class _FakeTexture:
    def create(self) -> bool:
        return True

    def destroy(self) -> None:
        pass


class _FakeRhi:
    def newTexture(self, *_args, **_kwargs) -> _FakeTexture:
        return _FakeTexture()


def _mounted_shell():
    """A shell with a live 2x2 texture, no real RHI (dedup probe only)."""
    from PySide6.QtCore import QSize

    from engine.overlay import TexturedOverlayShell

    shell = TexturedOverlayShell()
    shell.texture = _FakeTexture()
    shell.texture_size = QSize(2, 2)
    shell.rhi = _FakeRhi()
    # The resize path would normally rebuild the SRB/pipeline; the dedup
    # behavior under test does not depend on them.
    setattr(shell, "_build_srb", lambda: object())
    return shell


def test_textured_upload_frame_dedups_identical_content():
    shell = _mounted_shell()
    updates = _CountingUpdates()
    frame = (2, 2, bytes([1, 2, 3, 4]) * 4)

    assert shell.upload_frame(updates, None, frame) is True
    assert len(updates.uploads) == 1
    # Identical bytes, unchanged size: skip the upload, stay active.
    assert shell.upload_frame(updates, None, frame) is True
    assert len(updates.uploads) == 1
    assert shell.active is True


def test_textured_upload_frame_reuploads_changed_bytes():
    shell = _mounted_shell()
    updates = _CountingUpdates()
    shell.upload_frame(updates, None, (2, 2, bytes([1, 2, 3, 4]) * 4))
    # Changed (but same-size) content must land: no false hit.
    shell.upload_frame(updates, None, (2, 2, bytes([9, 9, 9, 9]) * 4))
    assert len(updates.uploads) == 2


def test_textured_upload_frame_reuploads_on_resize_and_resets_signature():
    from PySide6.QtCore import QSize

    shell = _mounted_shell()
    updates = _CountingUpdates()
    shell.upload_frame(updates, None, (2, 2, bytes([1, 2, 3, 4]) * 4))
    # Resize always uploads, then remembers the post-resize frame: a
    # second identical 4x4 frame dedups against that upload.
    big = (4, 4, bytes([5, 6, 7, 8]) * 16)
    shell.upload_frame(updates, None, big)
    assert len(updates.uploads) == 2
    assert shell.texture_size == QSize(4, 4)
    shell.upload_frame(updates, None, big)
    assert len(updates.uploads) == 2


def test_textured_upload_frame_force_bypasses_dedup():
    shell = _mounted_shell()
    updates = _CountingUpdates()
    frame = (2, 2, bytes([1, 2, 3, 4]) * 4)
    shell.upload_frame(updates, None, frame)
    shell.upload_frame(updates, None, frame, force=True)
    assert len(updates.uploads) == 2


def test_textured_upload_frame_none_deactivates():
    shell = _mounted_shell()
    updates = _CountingUpdates()
    assert shell.upload_frame(updates, None, None) is False
    assert shell.active is False
    assert updates.uploads == []


# ---------------------------------------------------------------------------
# F1 SHELL-PACKS (F1 owns this section; S1/S2/R3 sections above untouched).
#
# Pins the shell-side packing seam for scale-free resolvers
# (``src/engine/overlay/semantic.py``): engine-typed semantic structs +
# v2 resolver protocol plus pack functions emitting byte-identical uniform
# blocks for the five uniform families (divider / guides / capture /
# grid-dividers / arcs). The v1 byte-packing resolvers stay alive through
# the F-b..F-c coexistence window, so every frozen vector below proves
# v1-pack == v2-pack on this tree (ruling 5 byte-identity bar): divider /
# guides / capture replicate the pass-declared formats pinned to source
# text first, grid-dividers and arcs pack through the real v1 helpers
# (``_fb_rect_to_ndc_bounds`` / ``pack_arc_uniform``) imported live.
# ---------------------------------------------------------------------------

import struct as _struct

from engine.overlay import (
    DiskItem as _DiskItem,
)
from engine.overlay import (
    RectItem as _RectItem,
)
from engine.overlay import (
    Rgba as _Rgba,
)
from engine.overlay import (
    SemanticOverlayItems as _SemanticOverlayItems,
)
from engine.overlay import (
    SemanticResolver as _SemanticResolver,
)
from engine.overlay import (
    pack_arcs as _pack_arcs,
)
from engine.overlay import (
    pack_capture as _pack_capture,
)
from engine.overlay import (
    pack_divider as _pack_divider,
)
from engine.overlay import (
    pack_grid_dividers as _pack_grid_dividers,
)
from engine.overlay import (
    pack_guides as _pack_guides,
)

_F1_MATRIX = tuple(float(i) for i in range(16))
_F1_FB_W = 800.0
_F1_FB_H = 600.0

# Frozen pack outputs (hex): any byte drift in a pack function fails here.
_F1_DIVIDER_HEX = "000000000000803f0000004000004040000080400000a0400000c0400000e040000000410000104100002041000030410000404100005041000060410000704100004844000016440040c8430000c03f0000803f00000000000000000000803f000020410000a0410000434400000c4400000000000000000000000000000000"
_F1_GUIDES_HEX = "000000000000803f0000004000004040000080400000a0400000c0400000e040000000410000104100002041000030410000404100005041000060410000704100004844000016440000c842000016430000fa430000e143000040410000f04100002040000000000000000000000000000000000000803f000000000000003f"
_F1_CAPTURE_HEX = "000000000000803f0000004000004040000080400000a0400000c0400000e040000000410000104100002041000030410000404100005041000060410000704100004844000016440000c843000096430000404200004040000000000000000000000000000000000000803f0000803f"
_F1_GRID_HEX = "000000000000803f0000004000004040000080400000a0400000c0400000e0400000004100001041000020410000304100004041000050410000604100007041000000bfabaa2abf48e1fabeabaa2a3f0000803f0000803f0000803f0000803f"
_F1_ARCS_HEX = "000000000000803f0000004000004040000080400000a0400000c0400000e040000000410000104100002041000030410000404100005041000060410000704100004844000016440000c843000096430000704200000040000034420000b4420000803fd3d2d23eabaa2a3f0000803f"


def test_f1_semantic_import_seal():
    """semantic.py is engine-only: stdlib/Qt/engine imports, no app names."""
    text = read(OVERLAY / "semantic.py")
    tree = _parse(OVERLAY / "semantic.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if (node.level or 0) > 0:
                continue  # intra-package relative import (shell constants)
            top = node.module.split(".")[0]
            assert top in ("__future__", "dataclasses", "typing", "engine"), (
                f"src/engine/overlay/semantic.py:{node.lineno} imports "
                f"'{node.module}' -- engine overlay imports stdlib and "
                f"engine modules only"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in ("struct", "typing"), (
                    f"src/engine/overlay/semantic.py:{node.lineno} imports "
                    f"'{alias.name}' -- stdlib only"
                )
    for lineno, line in enumerate(text.splitlines(), start=1):
        assert "widget" not in line.lower(), (
            f"src/engine/overlay/semantic.py:{lineno} names 'widget' "
            f"({line.strip()[:80]!r}) -- packs take precomputed sizes"
        )
    assert "FULLSCREEN_VERTICES" in text, (
        "src/engine/overlay/semantic.py never references FULLSCREEN_VERTICES "
        "-- pack output renders through the shell quad shape, keep the tie"
    )


def test_f1_semantic_struct_shapes():
    """Frozen engine-typed structs + ctx-first v2 protocol (ruling 1)."""
    tree = _parse(OVERLAY / "semantic.py")
    classes = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    for name in ("Rgba", "RectItem", "DiskItem", "TextItem"):
        assert name in classes, f"semantic.py must declare {name}"
    rgba_fields = [t.target.id for t in classes["Rgba"].body if isinstance(t, ast.AnnAssign)]
    assert rgba_fields == ["r", "g", "b", "a"]
    rect_fields = [t.target.id for t in classes["RectItem"].body if isinstance(t, ast.AnnAssign)]
    assert rect_fields == ["x", "y", "w", "h", "color"]
    disk_fields = [t.target.id for t in classes["DiskItem"].body if isinstance(t, ast.AnnAssign)]
    assert disk_fields == ["cx", "cy", "radius", "line_width_key", "color", "extra"]
    text_fields = [t.target.id for t in classes["TextItem"].body if isinstance(t, ast.AnnAssign)]
    assert text_fields == ["rect", "text", "style"]
    for name in ("Rgba", "RectItem", "DiskItem", "TextItem"):
        assert "frozen=True" in _unparse(classes[name].decorator_list), (
            f"semantic.py {name} must be a frozen dataclass (immutable contract)"
        )
    assert "SemanticResolver" in classes, "semantic.py must declare SemanticResolver"
    resolver = classes["SemanticResolver"]
    assert any(
        isinstance(b, ast.Name)
        and b.id == "Protocol"
        or isinstance(b, ast.Subscript)
        and getattr(getattr(b, "value", None), "id", "") == "Protocol"
        for b in resolver.bases
    ) or "Protocol" in _unparse(resolver), (
        "SemanticResolver must be a typing.Protocol (structural seam)"
    )
    call = _methods(tree, "SemanticResolver").get("__call__")
    assert call is not None, "SemanticResolver must declare __call__"
    assert [a.arg for a in call.args.args][:2] == ["self", "ctx"], (
        "SemanticResolver.__call__ takes ctx first (engine types + opaque ctx)"
    )
    assert "SemanticOverlayItems" in _unparse(call.returns), (
        "SemanticResolver returns SemanticOverlayItems (scale-free geometry)"
    )
    union_src = _unparse(tree)
    for member in ("RectItem", "DiskItem", "TextItem"):
        assert member in union_src
    # Runtime surface: frozen structs construct, the union holds them, and a
    # ctx-first callable satisfies the structural protocol.
    probe = _RectItem(x=1.0, y=2.0, w=3.0, h=4.0, color=_Rgba(1.0, 1.0, 1.0, 1.0))
    items: _SemanticOverlayItems = (probe,)
    assert items[0] == probe
    assert isinstance(lambda ctx: items, _SemanticResolver)


def test_f1_bindings_reexports_v2_and_keeps_v1():
    """bindings.py re-exports the v2 protocol; v1 seam intact (ruling 2)."""
    tree = _parse(OVERLAY / "bindings.py")
    imported: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "semantic":
            imported[node.module] = [a.asname or a.name for a in node.names]
    assert "semantic" in imported, (
        "bindings.py must import the v2 protocol from .semantic"
    )
    for name in ("SemanticOverlayItems", "SemanticResolver"):
        assert name in imported["semantic"], (
            f"bindings.py must re-export {name} from .semantic"
        )
    # v1 intact: OverlayResolver/OverlayBinding still declared here.
    classes = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
    }
    assert "OverlayResolver" in classes and "OverlayBinding" in classes, (
        "bindings.py must keep declaring OverlayResolver + OverlayBinding "
        "through the coexistence window"
    )
    # Package surface exposes the full v2 vocabulary.
    init_text = read(OVERLAY / "__init__.py")
    for name in (
        "Rgba",
        "RectItem",
        "DiskItem",
        "TextItem",
        "SemanticOverlayItems",
        "SemanticResolver",
        "pack_divider",
        "pack_guides",
        "pack_capture",
        "pack_grid_dividers",
        "pack_arcs",
    ):
        assert name in init_text, (
            f"src/engine/overlay/__init__.py never exports {name}"
        )


def test_f1_shell_stage_packed_entry_point():
    """OverlayShell gains stage_packed; the seven stable entries stand."""
    tree = _parse(OVERLAY / "shell.py")
    methods = _methods(tree, "OverlayShell")
    for entry in (
        "mount",
        "ensure_slots",
        "stage_quad",
        "stage_slot",
        "clip_matrix",
        "draw",
        "teardown",
    ):
        assert entry in methods, (
            f"OverlayShell.{entry} missing -- F1 adds, never renames"
        )
    assert "stage_packed" in methods, (
        "OverlayShell.stage_packed missing -- the v2 semantic staging entry"
    )
    func = methods["stage_packed"]
    assert [a.arg for a in func.args.args] == [
        "self",
        "resource_updates",
        "blocks",
    ], "OverlayShell.stage_packed(resource_updates, blocks, *, start=0)"
    assert [a.arg for a in func.args.kwonlyargs] == ["start"], (
        "OverlayShell.stage_packed takes kw-only start"
    )

def test_f1_v1_layout_markers_still_pinned():
    """The v1 layouts the vectors replicate are still declared at source.

    Root tests must not deep-import tab internals (see
    ``test_root_tests_no_tab_internals_leak``), so the vectors replicate
    the v1 field order locally while this test pins the replicated facts
    to the v1 source text: a v1 layout change fails here loudly instead
    of silently comparing against a stale copy. Live-helper equality
    (real ``pack_arc_uniform`` / ``_fb_rect_to_ndc_bounds``) was proven
    once on this tree during F1 authoring and recorded in the wave notes.
    """
    markers = {
        # F2 migrated the IC passes to the v2 semantic seam
        # (lift-then-delete flag-day): layouts now live shell-side in
        # engine.overlay.semantic — the vectors replicate those, and this
        # pin keeps them tied to the single source of truth.
        "src/engine/overlay/semantic.py": (
            'DIVIDER_UNIFORM_FMT = "<24f4fi3f"',
            "DIVIDER_UNIFORM_SIZE = 128",
            'GUIDES_UNIFORM_FMT = "<32f"',
            "GUIDES_UNIFORM_SIZE = 128",
            'CAPTURE_UNIFORM_FMT = "<28f"',
            "CAPTURE_UNIFORM_SIZE = 112",
            'GRID_DIVIDER_UNIFORM_FMT = "<24f"',
            "GRID_DIVIDER_UNIFORM_SIZE = 96",
            'ARC_UNIFORM_FMT = "<16f2f2f4f4f"',
            "ARC_UNIFORM_SIZE = 112",
            "def pack_divider(",
            "def pack_arcs(",
            "def _fb_rect_to_ndc_bounds(",
            "(2.0 * x / fb_w) - 1.0",
            "1.0 - (2.0 * y / fb_h)",
        ),
        "src/tabs/multi_compare/canvas/features/grid_dividers/passes.py": (
            '_UNIFORM_FMT = "<24f"',
            "_UNIFORM_SIZE = 96",
        ),
        "src/tabs/image_compare/canvas/features/magnifier/render/passes_common.py": (
            "def pack_border_disk_uniform(",
        ),
        "src/tabs/image_compare/canvas/features/magnifier/render/shader_layout.py": (
            "ARC_UNIFORM_SIZE = 112",
            None,
        ),
    }
    offenders: list[str] = []
    for rel_path, wants in markers.items():
        text = read(ROOT / rel_path)
        for want in wants:
            if want is not None and want not in text:
                offenders.append(
                    f"{rel_path} lost {want!r} -- the F1 vector replicates it"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_f1_pack_divider_matches_v1():
    bar = _RectItem(
        x=399.0, y=50.0, w=3.0, h=500.0, color=_Rgba(1.0, 0.0, 0.0, 1.0)
    )
    clip = _RectItem(
        x=10.0, y=20.0, w=780.0, h=560.0, color=_Rgba(0.0, 0.0, 0.0, 0.0)
    )
    (block,) = _pack_divider((bar, clip), _F1_MATRIX, _F1_FB_W, _F1_FB_H)
    v1 = _struct.pack(
        "<24f4fi3f",
        *_F1_MATRIX,
        _F1_FB_W,
        _F1_FB_H,
        400.5,
        1.5,
        1.0,
        0.0,
        0.0,
        1.0,
        10.0,
        20.0,
        780.0,
        560.0,
        0,
        0.0,
        0.0,
        0.0,
    )
    assert len(block) == 128
    assert block == v1, "pack_divider drifted from the v1 divider block"
    assert block.hex() == _F1_DIVIDER_HEX


def test_f1_pack_guides_matches_v1():
    span = _DiskItem(
        cx=100.0,
        cy=150.0,
        radius=12.0,
        line_width_key="annotation_line_stroke_px",
        color=_Rgba(0.0, 1.0, 0.0, 0.5),
        extra=(500.0, 450.0, 30.0, 2.5),
    )
    (block,) = _pack_guides((span,), _F1_MATRIX, _F1_FB_W, _F1_FB_H)
    v1 = _struct.pack(
        "<32f",
        *_F1_MATRIX,
        _F1_FB_W,
        _F1_FB_H,
        100.0,
        150.0,
        500.0,
        450.0,
        12.0,
        30.0,
        2.5,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        0.0,
        0.5,
    )
    assert len(block) == 128
    assert block == v1, "pack_guides drifted from the v1 guides block"
    assert block.hex() == _F1_GUIDES_HEX


def test_f1_pack_capture_matches_v1():
    ring = _DiskItem(
        cx=400.0,
        cy=300.0,
        radius=48.0,
        line_width_key="annotation_ring_stroke_px",
        color=_Rgba(0.0, 0.0, 1.0, 1.0),
        extra=(3.0,),
    )
    (block,) = _pack_capture((ring,), _F1_MATRIX, _F1_FB_W, _F1_FB_H)
    v1 = _struct.pack(
        "<28f",
        *_F1_MATRIX,
        _F1_FB_W,
        _F1_FB_H,
        400.0,
        300.0,
        48.0,
        3.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
    )
    assert len(block) == 112
    assert block == v1, "pack_capture drifted from the v1 capture block"
    assert block.hex() == _F1_CAPTURE_HEX


def test_f1_pack_grid_dividers_matches_v1():
    rect = _RectItem(
        x=200.0, y=100.0, w=4.0, h=400.0, color=_Rgba(1.0, 1.0, 1.0, 1.0)
    )
    (block,) = _pack_grid_dividers((rect,), _F1_MATRIX, _F1_FB_W, _F1_FB_H)
    # v1 field order replicated locally (markers pinned to source above):
    # mat4 clip matrix + NDC bounds (x0, y0, x1, y1) + float RGBA.
    x0 = (2.0 * 200.0 / _F1_FB_W) - 1.0
    x1 = (2.0 * 204.0 / _F1_FB_W) - 1.0
    y_top = 1.0 - (2.0 * 100.0 / _F1_FB_H)
    y_bottom = 1.0 - (2.0 * 500.0 / _F1_FB_H)
    v1 = _struct.pack(
        "<24f", *_F1_MATRIX, x0, y_bottom, x1, y_top, 1.0, 1.0, 1.0, 1.0
    )
    assert len(block) == 96
    assert block == v1, "pack_grid_dividers drifted from the v1 NDC block"
    assert block.hex() == _F1_GRID_HEX


def test_f1_pack_arcs_matches_v1():
    pink = (1.0, 105.0 / 255.0, 170.0 / 255.0, 1.0)
    arc = _DiskItem(
        cx=400.0,
        cy=300.0,
        radius=60.0,
        line_width_key="annotation_arc_stroke_px",
        color=_Rgba(*pink),
        extra=(45.0, 90.0, True, True, 2.0),
    )
    (block,) = _pack_arcs((arc,), _F1_MATRIX, _F1_FB_W, _F1_FB_H)
    # v1 arc field order replicated locally (markers pinned to source
    # above): mat4 + fb size + center + radius/width/start/span + RGBA.
    v1 = _struct.pack(
        "<16f2f2f4f4f",
        *_F1_MATRIX,
        _F1_FB_W,
        _F1_FB_H,
        400.0,
        300.0,
        60.0,
        2.0,
        45.0,
        90.0,
        *pink,
    )
    assert len(block) == 112
    assert block == v1, "pack_arcs drifted from the v1 arc block"
    assert block.hex() == _F1_ARCS_HEX


def test_f1_canvas_scale_applies_shell_side():
    """Scale lives in the pack (never the resolver): 2x doubles geometry."""
    ring = _DiskItem(
        cx=400.0,
        cy=300.0,
        radius=48.0,
        line_width_key="annotation_ring_stroke_px",
        color=_Rgba(0.0, 0.0, 1.0, 1.0),
        extra=(3.0,),
    )
    (block,) = _pack_capture(
        (ring,), _F1_MATRIX, _F1_FB_W, _F1_FB_H, canvas_scale=2.0
    )
    v1 = _struct.pack(
        "<28f",
        *_F1_MATRIX,
        _F1_FB_W,
        _F1_FB_H,
        800.0,
        600.0,
        96.0,
        6.0,
        0.0,
        0.0,
        0.0,
        0.0,
        1.0,
        1.0,
    )
    assert block == v1, "canvas_scale must scale geometry, never color/matrix/fb"
    # Default scale is the identity: explicit 1.0 matches the frozen vector.
    (default,) = _pack_capture((ring,), _F1_MATRIX, _F1_FB_W, _F1_FB_H)
    (explicit,) = _pack_capture(
        (ring,), _F1_MATRIX, _F1_FB_W, _F1_FB_H, canvas_scale=1.0
    )
    assert default == explicit
    assert default.hex() == _F1_CAPTURE_HEX
