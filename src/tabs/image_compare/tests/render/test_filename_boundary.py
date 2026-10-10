"""F5 filename-verdict boundary pins (BOUNDARY, not a migration).

Pins the three-part verdict documented on ``FilenameOverlayPass`` and in
``render/gpu_resources.py`` mechanically.
Variant C1 re-open (2026-10-06): the per-string CPU raster + 4x supersample +
GPU Lanczos downsample of variant A are GONE. Text is per-glyph quads sampling
one shared signed-distance-field atlas (``render/glyph_atlas.py``); the
rounded-rect background is a mode-0 quad through the same pipeline.

(1) WHAT STAYS -- one shared SDF atlas texture + linear/nearest samplers, a
    four-attribute vertex layout (pos / uv / color / mode+weight), per-slot
    growable vertex buffers holding the background quad plus N glyph quads,
    per-slot 128-byte uniform blocks, and per-slot N-quad screen draws.
(2) ORDERING -- ``record()`` only draws (no uploadTexture / beginPass); the
    atlas upload happens in ``prepare()`` through the shared resource batch,
    and there is no device-resolve pre-pass anymore.
(3) SHELL SHAPE -- ``TexturedOverlayShell`` keeps the shape the verdict was
    measured against (one texture, fullscreen quad, one srb, no atlas, no
    N-quad stream); if the shell ever gains the filename shape, this file
    fails and the verdict re-opens (invalidation condition).

No behavior change -- file reads + AST only, no Qt, no GPU.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[5]
_FN = _REPO / "src" / "tabs" / "image_compare" / "canvas" / "features" / "filename_overlay"
_PASSES = _FN / "passes.py"
_GPU = _FN / "render" / "gpu_resources.py"
_ATLAS = _FN / "render" / "glyph_atlas.py"
_TEXT_RUN = _FN / "render" / "text_run.py"
_FRAG_OVERLAY = _FN / "shaders" / "filename_overlay.frag"
_VERT_OVERLAY = _FN / "shaders" / "filename_overlay.vert"
_SHELL = _REPO / "src" / "engine" / "overlay" / "textured.py"

# The retired variant-A cluster; none of these names may come back.
_RETIRED = (
    "label_downsample",
    "srb_downsample",
    "downsample_target",
    "downsample_rpdesc",
    "downsample_pipeline",
    "newTextureRenderTarget",
    "raw_texture",
    "needs_downsample",
    "pending_upload_image",
    "_LABEL_SUPERSAMPLE",
    "rasterize_label",
)


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
    atlas_text = _read(_ATLAS)
    for marker in ("WHAT STAYS", "INVALIDATION"):
        assert marker in passes_text, f"passes.py lost verdict marker {marker!r}"
        assert marker in gpu_text, f"gpu_resources.py lost verdict marker {marker!r}"
    assert "TexturedOverlayShell" in passes_text
    assert "TexturedOverlayShell" in gpu_text
    assert "TexturedOverlayShell" in atlas_text


def test_filename_c1_atlas_owns_the_sdf():
    """C1 stay: one shared SDF atlas, built CPU-side (texture owner is gpu)."""
    atlas_text = _read(_ATLAS)
    for marker in (
        "class GlyphAtlas",
        "def ensure",
        "def glyph_for",
        "distance_transform_edt",
        "signed_distance",
        "class GlyphSlot",
    ):
        assert marker in atlas_text, f"glyph_atlas.py lost marker {marker!r}"
    assert "newTexture" not in atlas_text, (
        "glyph_atlas.py allocates a QRhi texture -- atlas texture ownership "
        "stays in render/gpu_resources.py (pinned texture owners)"
    )


def test_filename_gpu_resources_hold_atlas_and_quads_not_the_old_cluster():
    """C1 resource shape: atlas + per-slot N-quad buffers, no supersample."""
    gpu_text = _read(_GPU)
    for marker in (
        "ensure_atlas",
        "atlas_texture",
        "sampler_linear",
        "sampler_nearest",
        "ensure_vertex_capacity",
        "vertex_capacity",
        "uniform_buffer",
        "QRhiGraphicsPipeline.Topology.Triangles",
    ):
        assert marker in gpu_text, f"gpu_resources.py lost C1 marker {marker!r}"
    for marker in _RETIRED:
        assert marker not in gpu_text, (
            f"gpu_resources.py still carries retired variant-A symbol {marker!r} "
            f"-- C1 deleted that cluster"
        )


def test_filename_shaders_are_sdf_glyph_quads():
    """C1 shader shape: per-glyph SDF quads + procedural bg, no downsample."""
    vert = _read(_VERT_OVERLAY)
    for marker in ("mvp", "aPos", "aUV", "aColor", "aAux", "bgColor"):
        assert marker in vert, f"filename_overlay.vert lost marker {marker!r}"
    frag = _read(_FRAG_OVERLAY)
    for marker in (
        "roundedBoxSdf",
        "bgColor",
        "quadSizePx",
        "cornerRadiusPx",
        "bgEnabled",
        "sdfRangePx",
        "pixelSize",
        "edgePx",
        "smoothstep",
        "vAux",
    ):
        assert marker in frag, f"filename_overlay.frag lost SDF marker {marker!r}"
    for stale in ("label_downsample.vert", "label_downsample.frag"):
        assert not (_FN / "shaders" / stale).exists(), (
            f"retired shader {stale!r} is back -- C1 deleted it"
        )


def test_filename_passes_pack_runs_and_draw_n_quads():
    """C1 pass: pack_run + pack_bg_quad, growable buffers, N-quad draw."""
    passes_text = _read(_PASSES)
    for marker in (
        "pack_run",
        "pack_bg_quad",
        "ensure_vertex_capacity",
        "slot.vertex_count",
        "_pixel_space_mvp",
        "sdf_range_px",
    ):
        assert marker in passes_text, f"passes.py lost C1 marker {marker!r}"
    for marker in _RETIRED:
        assert marker not in passes_text, (
            f"passes.py still carries retired variant-A symbol {marker!r}"
        )
    assert "_MATRIX_UNIFORM_FMT = \"<32f\"" in passes_text
    assert "_UNIFORM_SIZE" in passes_text and "assert_uniform_size" in passes_text


def test_filename_record_only_draws():
    """Ordering: record() draws only; prepare() stages the atlas upload."""
    methods = _methods(_PASSES, "FilenameOverlayPass")
    record = methods.get("record", "")
    prepare = methods.get("prepare", "")
    assert record, "FilenameOverlayPass.record disappeared"
    assert "uploadTexture" not in record, (
        "FilenameOverlayPass.record calls uploadTexture -- uploads belong in "
        "prepare's shared resource batch, not the draw recorder"
    )
    assert "beginPass" not in record, (
        "FilenameOverlayPass.record opens a pass -- C1 has no device-resolve "
        "pre-pass; draws happen inside the main pass only"
    )
    assert "uploadTexture" in prepare, (
        "FilenameOverlayPass.prepare no longer stages the atlas upload"
    )
    assert "ensure_atlas" in prepare, (
        "FilenameOverlayPass.prepare no longer builds/refreshes the atlas"
    )
    assert "record_pre_pass" not in methods, (
        "FilenameOverlayPass.record_pre_pass is back -- C1 deleted the "
        "device-resolve pre-pass (no downsample nesting)"
    )


def test_textured_shell_shape_unchanged():
    """Shell half of the verdict: single-texture fullscreen shape, no slots.

    If the shell gains an atlas + per-glyph quad stream, this fails and the F5
    verdict re-opens (invalidation condition) -- do not "fix" by weakening the
    pins.
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
        "GlyphAtlas",
        "pack_run",
    ):
        assert marker not in shell_text, (
            f"textured.py gained {marker!r} -- the shell now overlaps the "
            f"filename shape; re-open the F5 verdict (invalidation)"
        )
