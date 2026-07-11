"""Shared QRhi shader location + uniform-block sizes for the magnifier passes."""

from __future__ import annotations

from pathlib import Path

SHADER_DIR = Path(__file__).resolve().parent.parent / "shaders" / "qrhi"

ARC_UNIFORM_SIZE = 112
BORDER_DISK_UNIFORM_SIZE = 128
MAG_UNIFORM_SIZE = 256
