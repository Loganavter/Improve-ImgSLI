from __future__ import annotations

import logging
from shared.rendering import NormalizedBounds
from tabs.image_compare.video_editor.services.video_export_models import GlobalCanvasBounds

_blog = logging.getLogger("ImproveImgSLI.bounds_analyzer")

class CanvasBoundsAnalyzer:
    def __init__(self, image_loader) -> None:
        self._image_loader = image_loader

    def calculate(self, snapshots, auto_crop: bool = False) -> GlobalCanvasBounds | None:
        if not snapshots:
            return None
        tab_bounds = self._calculate_tab_bounds(snapshots, auto_crop=auto_crop)
        if tab_bounds is not None:
            return tab_bounds
        return self._calculate_featureless_bounds(snapshots, auto_crop=auto_crop)

    def _calculate_tab_bounds(self, snapshots, *, auto_crop: bool):
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        registry.discover()
        return registry.create_service(
            "global_canvas_bounds",
            snapshots,
            self._image_loader,
            auto_crop,
        )

    def _calculate_featureless_bounds(self, snapshots, *, auto_crop: bool):
        base_w, base_h = 0, 0

        for snap in snapshots:
            for source in snap.sources:
                img = self._image_loader(source, auto_crop)
                if img:
                    w, h = img.size
                    base_w = max(base_w, w)
                    base_h = max(base_h, h)

        if base_w == 0 or base_h == 0:
            return None

        _blog.info(
            "BOUNDS base=%sx%s layout_requirement_commands=%s snapshots=%s",
            base_w, base_h, 0,
            len(snapshots),
        )

        final_canvas_bounds = NormalizedBounds.unit()
        return GlobalCanvasBounds(
            pad_left=0,
            pad_right=0,
            pad_top=0,
            pad_bottom=0,
            base_width=base_w,
            base_height=base_h,
            canvas_x_min=float(final_canvas_bounds.x_min),
            canvas_x_max=float(final_canvas_bounds.x_max),
            canvas_y_min=float(final_canvas_bounds.y_min),
            canvas_y_max=float(final_canvas_bounds.y_max),
        )
