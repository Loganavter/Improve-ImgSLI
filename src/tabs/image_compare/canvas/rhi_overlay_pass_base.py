"""Shared QRhi fullscreen textured-overlay pass base for Image Compare features.

Mirrors ``tabs.multi_compare.canvas.rhi_overlay_pass_base`` for image_compare:
rasterize into a framebuffer-sized QImage and draw it as one alpha-blended
textured quad — shared QRhi plumbing (pipeline, texture, SRB, blend);
subclasses implement ``_raster``.
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhi,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiTexture,
    QRhiViewport,
)

from ui.canvas_infra.scene.pass_contract import CanvasRenderPass

logger = logging.getLogger("ImproveImgSLI")

# Shared shader dir — overlay shaders are generic fullscreen textured quad.
# Prefer local image_compare copy if present, else reuse multi_compare's.
_LOCAL_SHADER_DIR = Path(__file__).resolve().parent / "shaders" / "overlay"
_MC_SHADER_DIR = Path(__file__).resolve().parents[2] / "multi_compare" / "shaders" / "qrhi"

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
OVERLAY_UNIFORM_SIZE = 64


def _shader_dir() -> Path:
    if _LOCAL_SHADER_DIR.is_dir():
        return _LOCAL_SHADER_DIR
    return _MC_SHADER_DIR


def _load_shader(name: str):
    from PySide6.QtGui import QShader

    data = (_shader_dir() / name).read_bytes()
    shader = QShader.fromSerialized(data)
    if not shader.isValid():
        raise RuntimeError(f"Invalid overlay shader: {name}")
    return shader


def _vertex_input_layout():
    from PySide6.QtGui import QRhiVertexInputAttribute, QRhiVertexInputBinding, QRhiVertexInputLayout

    layout = QRhiVertexInputLayout()
    layout.setBindings([QRhiVertexInputBinding(16)])
    layout.setAttributes(
        [
            QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
            QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
        ]
    )
    return layout
