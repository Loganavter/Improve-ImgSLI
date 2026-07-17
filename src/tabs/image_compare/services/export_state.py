"""Shim: state coordinator lives in ``image_export.state``."""

from __future__ import annotations

from tabs.image_compare.services.image_export.state import ExportStateCoordinator

__all__ = ["ExportStateCoordinator"]
