"""Mutable cache bags owned by SnapshotFrameRenderer."""

from __future__ import annotations

from shared.rendering.image_identity import image_uid

from tabs.image_compare.services.video_snapshot_rendering.models import ImagePrepCacheEntry


class FrameRenderCaches:
    """Prescale / image-prep / scene-image caches for one renderer instance."""

    __slots__ = ("prescaled", "image_prep", "scene_images")

    def __init__(self) -> None:
        self.prescaled: tuple | None = None
        self.image_prep: tuple[object, ImagePrepCacheEntry] | None = None
        self.scene_images: dict = {}

    def clear(self) -> None:
        self.prescaled = None
        self.image_prep = None
        self.scene_images = {}

    @staticmethod
    def image_prep_key(
        img1,
        img2,
        request,
        scaled_global_bounds,
        resize_method,
        normalize_snapshot,
    ):
        bounds_key = None
        if scaled_global_bounds is not None:
            bounds_key = (
                int(scaled_global_bounds.pad_left),
                int(scaled_global_bounds.pad_right),
                int(scaled_global_bounds.pad_top),
                int(scaled_global_bounds.pad_bottom),
                int(scaled_global_bounds.base_width),
                int(scaled_global_bounds.base_height),
            )
        return (
            image_uid(img1),
            image_uid(img2),
            img1.size if img1 else None,
            img2.size if img2 else None,
            request.fit_content,
            bounds_key,
            request.target_surface.fill_rgba,
            resize_method,
            request.target_surface.width,
            request.target_surface.height,
            bool(normalize_snapshot),
        )
