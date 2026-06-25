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
    -1.0, 1.0, 0.0, 0.0,
    -1.0, -1.0, 0.0, 1.0,
    1.0, 1.0, 1.0, 0.0,
    1.0, -1.0, 1.0, 1.0,
)
SLOT_UNIFORM_SIZE = 96
OVERLAY_UNIFORM_SIZE = 64


def load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid multi_compare shader: {name}")
    return shader


def vertex_input_layout() -> QRhiVertexInputLayout:
    layout = QRhiVertexInputLayout()
    layout.setBindings([QRhiVertexInputBinding(VERTEX_STRIDE)])
    layout.setAttributes([
        QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
        QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
    ])
    return layout
