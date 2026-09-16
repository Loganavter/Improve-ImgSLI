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
"""

from __future__ import annotations

import ast
import re

from ._framework import ROOT, read

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
    return ast.parse(read(path))


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
        ) and str(size) not in text:
            offenders.append(f"{rel_path} declares no uniform_size={size}")
        if "OverlayResolver" not in text:
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
    assert files == ["__init__.py", "bindings.py", "shell.py", "views.py"], (
        f"src/engine/overlay/ holds the shell + seam only: {files}"
    )


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
        try:
            tree = ast.parse(text)
        except SyntaxError:
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


def test_mc_raster_pins_stay_on_texture_shell():
    """Pin reason: glyph/interaction raster needs texture upload, which the
    uniform-only OverlayShell cannot host (no texture/sampler entry points).
    """
    base_text = read(ROOT / _MC_TEXTURE_BASE)
    assert "uploadTexture" in base_text and "sampledTexture" in base_text, (
        f"{_MC_TEXTURE_BASE} must keep the texture-upload path -- it is the "
        f"pin reason for both raster passes"
    )
    offenders: list[str] = []
    for source_path, shell_path in _MC_TEXTURE_PINS.items():
        shell_text = read(ROOT / shell_path)
        shell_tree = _parse(ROOT / shell_path)
        subclasses = any(
            isinstance(node, ast.ClassDef)
            and node.name.endswith("Pass")
            and any(
                _unparse(base) == "FullscreenOverlayTexturePass"
                for base in node.bases
            )
            for node in ast.walk(shell_tree)
        )
        if not subclasses:
            offenders.append(
                f"{shell_path} no longer subclasses "
                f"FullscreenOverlayTexturePass -- the raster pin assumes "
                f"the texture shell (S6 moves it only with a textured "
                f"engine shell, never the uniform one)"
            )
        if "from engine.overlay import" in shell_text or (
            "from engine.overlay" in shell_text
        ):
            offenders.append(
                f"{shell_path} imports engine.overlay -- pinned shells stay "
                f"pass-owned until a textured engine shell exists"
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
    for name in ("shell.py", "views.py"):
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
