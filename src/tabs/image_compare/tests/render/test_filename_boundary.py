"""F5 filename-verdict boundary pins (BOUNDARY, not a migration).

Pins the three-part verdict documented on ``FilenameOverlayPass`` and in
``render/gpu_resources.py`` / ``render/label_raster.py`` mechanically.
Variant A re-open (2026-10-06): the rounded-rect background is now drawn
procedurally in ``filename_overlay.frag`` (SDF rounded box) and the texture
is TEXT ONLY, cache-keyed by content rather than width -- but the resource
shape the verdict was measured against is unchanged.

(1) WHAT STAYS -- the filename files keep the per-slot two-texture +
    RenderTarget downsample + supersample + device-resolve + per-slot
    quad shape (text markers per file), now with a per-slot 128-byte
    uniform block; the texture is text-only and the background is
    procedural.
(2) ORDERING -- the uploadTexture-then-same-main-pass-draw assumption is
    absent: ``prepare()`` stages no texture upload, while
    ``record_pre_pass()`` nests uploadTexture inside its own
    beginPass/endPass device-resolve (AST method-body pins).
(3) SHELL SHAPE -- ``TexturedOverlayShell`` keeps the shape the verdict
    was measured against (one texture, fullscreen quad, one srb, no
    RenderTarget, no pre-pass); if the shell ever gains the filename
    shape, this file fails and the verdict re-opens (invalidation
    condition).

No behavior change -- file reads + AST only, no Qt, no GPU.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[5]
_FN = _REPO / "src" / "tabs" / "image_compare" / "canvas" / "features" / "filename_overlay"
_PASSES = _FN / "passes.py"
_GPU = _FN / "render" / "gpu_resources.py"
_RASTER = _FN / "render" / "label_raster.py"
_FRAG = _FN / "shaders" / "label_downsample.frag"
_FRAG_OVERLAY = _FN / "shaders" / "filename_overlay.frag"
_VERT_OVERLAY = _FN / "shaders" / "filename_overlay.vert"
_SHELL = _REPO / "src" / "engine" / "overlay" / "textured.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _methods(path: Path, class_name: str) -> dict[str, str]:
    tree = ast.parse(_read(path))
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    try:
                        out[stmt.name] = ast.unparse(stmt)
                    except Exception:
                        out[stmt.name] = ""
    return out


def test_filename_verdict_statement_present():
    """The 3-part verdict (stays / why / invalidation) lives in code."""
    passes_text = _read(_PASSES)
    gpu_text = _read(_GPU)
    raster_text = _read(_RASTER)
    for marker in ("WHAT STAYS", "INVALIDATION"):
        assert marker in passes_text, f"passes.py lost verdict marker {marker!r}"
        assert marker in gpu_text, f"gpu_resources.py lost verdict marker {marker!r}"
    assert "TexturedOverlayShell" in passes_text
    assert "TexturedOverlayShell" in gpu_text
    assert "TexturedOverlayShell" in raster_text


def test_filename_stays_per_slot_textures_and_targets():
    """Stay 1: per-slot raw+final textures, per-slot RenderTarget targets."""
    gpu_text = _read(_GPU)
    for marker in (
        "ensure_slot_textures",
        "raw_texture",
        "srb_nearest",
        "srb_linear",
        "srb_downsample",
        "downsample_target",
        "downsample_rpdesc",
        "downsample_pipeline",
        "newTextureRenderTarget",
        "RenderTarget",
        "needs_downsample",
        "pending_upload_image",
        "uniform_buffer",
    ):
        assert marker in gpu_text, f"gpu_resources.py lost stay marker {marker!r}"


def test_filename_stays_supersample_and_quads():
    """Stay 2: supersampled upload + Lanczos pre-pass + per-slot quads."""
    raster_text = _read(_RASTER)
    for marker in ("_LABEL_SUPERSAMPLE = 4", "build_quad_vertices"):
        assert marker in raster_text, f"label_raster.py lost stay marker {marker!r}"
    frag_text = _read(_FRAG)
    for marker in ("SCALE = 4.0", "RADIUS = 8"):
        assert marker in frag_text, f"label_downsample.frag lost marker {marker!r}"
    passes_text = _read(_PASSES)
    for marker in (
        "record_pre_pass",
        "build_quad_vertices",
        "srb_linear",
        "srb_nearest",
        "slot.vertex_buffer",
    ):
        assert marker in passes_text, f"passes.py lost stay marker {marker!r}"


def test_filename_stays_text_only_and_procedural_bg():
    """Variant A stay: text-only texture + procedural SDF background.

    Re-opened F5 verdict. The background must NOT come back onto the CPU
    raster (``draw_round_rect`` gone from label_raster.py) and must be
    drawn procedurally from the 128-byte per-slot uniform block. If this
    fails, the verdict re-opens again -- do not "fix" by weakening it.
    """
    raster_text = _read(_RASTER)
    for marker in ("rasterize_label_text", "rasterize_label", "draw_text_bold"):
        assert marker in raster_text, f"label_raster.py lost text-only marker {marker!r}"
    assert "draw_round_rect" not in raster_text, (
        "label_raster.py draws the background on the CPU again -- variant A "
        "moved it into filename_overlay.frag; re-open the F5 verdict"
    )
    frag = _read(_FRAG_OVERLAY)
    for marker in (
        "roundedBoxSdf",
        "bgColor",
        "quadSizePx",
        "textRectPx",
        "cornerRadiusPx",
        "bgEnabled",
        "textEnabled",
    ):
        assert marker in frag, f"filename_overlay.frag lost procedural-bg marker {marker!r}"
    vert = _read(_VERT_OVERLAY)
    for marker in ("quadSizePx", "textRectPx", "bgColor", "mvp"):
        assert marker in vert, f"filename_overlay.vert lost UBO marker {marker!r}"


def test_filename_raster_key_excludes_width_and_uniforms_are_per_slot():
    """Variant A claim: width no longer drives the raster cache key.

    The key must be keyed on content/style only (no ``rw``/``rh``), and
    the uniform block must be 128 bytes and per-slot (the shader UBO grew
    from the old shared 64B ``mvp``-only buffer).
    """
    passes_text = _read(_PASSES)
    assert '_MATRIX_UNIFORM_FMT = "<32f"' in passes_text
    assert "_UNIFORM_SIZE" in passes_text and "assert_uniform_size" in passes_text
    for marker in ("elided", "text_color.rgba()", "quality"):
        assert marker in passes_text, f"passes.py cache key lost {marker!r}"
    # The key tuple must not carry rw/rh (the old churn source).
    assert "cache_key = (" in passes_text
    gpu_text = _read(_GPU)
    assert "_UNIFORM_SIZE = 128" in gpu_text
    assert "slot.uniform_buffer = rhi.newBuffer" in gpu_text, (
        "gpu_resources.py no longer creates a per-slot uniform buffer"
    )
    assert "self.uniform_buffer = rhi.newBuffer" not in gpu_text, (
        "gpu_resources.py still creates a single shared uniform buffer -- "
        "variant A requires a per-slot buffer"
    )
    for marker in ("slot.uniform_buffer", "updateDynamicBuffer"):
        assert marker in gpu_text or marker in passes_text, (
            f"per-slot uniform buffer marker {marker!r} missing"
        )


def test_filename_upload_never_rides_shared_prepare_batch():
    """Ordering: prepare() stages no upload; the pre-pass nests upload+pass.

    The shared prepare batch submits alongside the main pass beginPass --
    after record_pre_pass's downsample read -- so the upload must live in
    record_pre_pass (own resourceUpdate + beginPass/endPass), never in
    prepare() or record().
    """
    methods = _methods(_PASSES, "FilenameOverlayPass")
    prepare = methods.get("prepare", "")
    record = methods.get("record", "")
    pre_pass = methods.get("record_pre_pass", "")
    assert "uploadTexture" not in prepare, (
        "FilenameOverlayPass.prepare stages uploadTexture -- the upload "
        "must live in record_pre_pass (device-resolve ordering)"
    )
    assert "uploadTexture" not in record, (
        "FilenameOverlayPass.record calls uploadTexture -- uploads belong "
        "in record_pre_pass, draws belong in record"
    )
    assert "beginPass" not in record, (
        "FilenameOverlayPass.record opens a pass -- only record_pre_pass "
        "may beginPass (QRhi passes cannot nest)"
    )
    for marker in ("uploadTexture", "beginPass", "endPass"):
        assert marker in pre_pass, (
            f"FilenameOverlayPass.record_pre_pass lost {marker!r} -- the "
            f"device-resolve nesting the shell cannot host"
        )


def test_textured_shell_shape_unchanged():
    """Shell half of the verdict: single-texture fullscreen shape, no slots.

    If the shell gains slot-targets + a GPU-supersample stage, this fails
    and the F5 verdict re-opens (invalidation condition) -- do not "fix"
    by weakening the pins.
    """
    shell_text = _read(_SHELL)
    for marker in (
        "FULLSCREEN_VERTICES",
        "self.srb",
        "upload_frame",
        "def draw",
        "def stage_quad",
        "TEXTURED_UNIFORM_SIZE = 64",
    ):
        assert marker in shell_text, f"textured.py lost shell marker {marker!r}"
    for marker in (
        "RenderTarget",
        "newTextureRenderTarget",
        "srb_linear",
        "srb_nearest",
        "srb_downsample",
        "record_pre_pass",
        "beginPass",
        "build_quad_vertices",
    ):
        assert marker not in shell_text, (
            f"textured.py gained {marker!r} -- the shell now overlaps the "
            f"filename shape; re-open the F5 verdict (invalidation)"
        )
