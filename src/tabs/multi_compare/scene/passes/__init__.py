"""Local render passes for the Multi Compare scene."""

from tabs.multi_compare.scene.passes.base_images import RENDER_PASSES, BaseImagesPass
from tabs.multi_compare.scene.passes.dividers import DividersOverlaySource
from tabs.multi_compare.scene.passes.drag_overlay import DragDropOverlaySource
from tabs.multi_compare.scene.passes.labels import LabelsOverlaySource

__all__ = [
    "RENDER_PASSES",
    "BaseImagesPass",
    "DividersOverlaySource",
    "DragDropOverlaySource",
    "LabelsOverlaySource",
]
