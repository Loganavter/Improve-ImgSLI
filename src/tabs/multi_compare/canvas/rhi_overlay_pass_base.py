"""Shared QRhi fullscreen textured-overlay pass base for Multi Compare features.

``layer_labels`` and ``drag_drop_overlay`` rasterize into an independent
framebuffer-sized ``QImage`` and draw it as one alpha-blended textured quad —
shared QRhi plumbing (pipeline, texture, SRB, blend); subclasses implement
``_raster``. Grid dividers use a dedicated GPU quad pass instead (no FB-sized
overlay texture). Split out in B3: two features rasterize the same
framebuffer-sized quad, so the QRhi plumbing belongs in one base class, not
twice.
"""

from __future__ import annotations

import logging
import struct

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

from tabs.multi_compare.scene.resources import (
    FULLSCREEN_VERTICES,
    OVERLAY_UNIFORM_SIZE,
    load_shader,
    vertex_input_layout,
)
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)
