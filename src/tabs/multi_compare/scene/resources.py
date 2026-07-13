"""Shared QRhi resource helpers for Multi Compare scene passes."""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtGui import (
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QShader,
)

SHADER_DIR = Path(__file__).resolve().parent.parent / "shaders" / "qrhi"
VERTEX_STRIDE = 16
FULLSCREEN_VERTICES = struct.pack(
    "<16f",
    -1.0,
    1.0,
    0.0,
    0.0,
    -1.0,
    -1.0,
    0.0,
    1.0,
    1.0,
    1.0,
    1.0,
    0.0,
    1.0,
    -1.0,
    1.0,
    1.0,
)
# std140 layout of multi_compare.frag/vert's UBuf: mat4 mvp(64) +
# vec2 panOffset(8) + vec2 fitScale(8) + float zoom(4) + 12B pad +
# vec4 tileRect(16) = 112. tileRect carries the currently-drawn GPU tile's
# rect in normalized slot-image space (docs/dev/TILED_RENDERING_DESIGN.md
# pattern, reused here via shared.rendering.tile_texture_service); identity
# (0,0,1,1) reproduces pre-tiling behavior unchanged.
SLOT_UNIFORM_SIZE = 112
OVERLAY_UNIFORM_SIZE = 64
# Mirrors image_compare's rhi_renderer/resources.py _LIVE_TILE_EXTENT /
# _TILE_CACHE_BUDGET_BYTES (docs/dev/TILED_RENDERING_DESIGN.md Phase 2):
# fixed tile size so residency/eviction behavior is deterministic across
# machines, clamped by the backend's real max texture size defensively at
# renderer initialize() time. Budget is shared across every slot's resident
# tiles combined, since GPU memory is one pool, not N independent ones.
SLOT_LIVE_TILE_EXTENT = 8192
SLOT_TILE_CACHE_BUDGET_BYTES = 512 * 1024 * 1024


def load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid multi_compare shader: {name}")
    return shader


def vertex_input_layout() -> QRhiVertexInputLayout:
    layout = QRhiVertexInputLayout()
    layout.setBindings([QRhiVertexInputBinding(VERTEX_STRIDE)])
    layout.setAttributes(
        [
            QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
            QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
        ]
    )
    return layout
