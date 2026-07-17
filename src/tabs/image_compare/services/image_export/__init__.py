"""Still-image export pipeline for image_compare tab."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tabs.image_compare.services.image_export.models import ExportSaveContext

if TYPE_CHECKING:
    from tabs.image_compare.services.image_export.context_builder import ExportContextBuilder
    from tabs.image_compare.services.image_export.save_flow import ExportSaveFlowCoordinator
    from tabs.image_compare.services.image_export.service import ExportService
    from tabs.image_compare.services.image_export.state import ExportStateCoordinator

__all__ = [
    "ExportContextBuilder",
    "ExportSaveContext",
    "ExportSaveFlowCoordinator",
    "ExportService",
    "ExportStateCoordinator",
]


def __getattr__(name: str):
    if name == "ExportStateCoordinator":
        from tabs.image_compare.services.image_export.state import ExportStateCoordinator

        return ExportStateCoordinator
    if name == "ExportContextBuilder":
        from tabs.image_compare.services.image_export.context_builder import (
            ExportContextBuilder,
        )

        return ExportContextBuilder
    if name == "ExportSaveFlowCoordinator":
        from tabs.image_compare.services.image_export.save_flow import (
            ExportSaveFlowCoordinator,
        )

        return ExportSaveFlowCoordinator
    if name == "ExportService":
        from tabs.image_compare.services.image_export.service import ExportService

        return ExportService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
