from __future__ import annotations

from core.store import Store
from plugins.video_editor.services.video_export_models import GlobalCanvasBounds
from ui.canvas_features.magnifier import compute_magnifier_padding, iter_magnifier_models

class CanvasBoundsAnalyzer:
    def __init__(self, image_loader) -> None:
        self._image_loader = image_loader

    def calculate(self, snapshots, auto_crop: bool = False) -> GlobalCanvasBounds | None:
        if not snapshots:
            return None

        max_pad_left = 0
        max_pad_right = 0
        max_pad_top = 0
        max_pad_bottom = 0
        base_w, base_h = 0, 0

        for snap in snapshots:
            img1 = self._image_loader(snap.image1_path, auto_crop)
            if img1:
                w, h = img1.size
                base_w = max(base_w, w)
                base_h = max(base_h, h)

            img2 = self._image_loader(snap.image2_path, auto_crop)
            if img2:
                w, h = img2.size
                base_w = max(base_w, w)
                base_h = max(base_h, h)

        if base_w == 0 or base_h == 0:
            return None

        for snap in snapshots:
            visible_models = [
                model
                for model in iter_magnifier_models(
                    snap.viewport_state.view_state,
                    snap.viewport_state.render_config,
                )
                if bool(model.visible)
            ]
            if not visible_models:
                continue

            img1 = self._image_loader(snap.image1_path, auto_crop)
            img2 = self._image_loader(snap.image2_path, auto_crop)
            if not img1 or not img2:
                continue

            temp_store = Store()
            temp_store.viewport = snap.viewport_state.clone()
            temp_store.settings = snap.settings_state.freeze_for_export()
            temp_store.viewport.session_data.image_state.image1 = img1
            temp_store.viewport.session_data.image_state.image2 = img2
            temp_store.document.full_res_image1 = img1
            temp_store.document.full_res_image2 = img2
            temp_store.viewport.geometry_state.pixmap_width = base_w
            temp_store.viewport.geometry_state.pixmap_height = base_h

            pad_left, pad_right, pad_top, pad_bottom = compute_magnifier_padding(
                temp_store,
                drawing_width=base_w,
                drawing_height=base_h,
            )
            max_pad_left = max(max_pad_left, pad_left)
            max_pad_right = max(max_pad_right, pad_right)
            max_pad_top = max(max_pad_top, pad_top)
            max_pad_bottom = max(max_pad_bottom, pad_bottom)

        return GlobalCanvasBounds(
            pad_left=max_pad_left,
            pad_right=max_pad_right,
            pad_top=max_pad_top,
            pad_bottom=max_pad_bottom,
            base_width=base_w,
            base_height=base_h,
        )
