"""Source image loading for snapshot frames."""

from __future__ import annotations

from PIL import Image

from tabs.image_compare.plugins.video_editor.services.video_export_models import (
    VideoRenderRequest,
)


def resolve_images(image_loader, snap, request: VideoRenderRequest):
    img1 = image_loader(snap.image1_path, request.auto_crop)
    img2 = image_loader(snap.image2_path, request.auto_crop)

    if not img1:
        img1 = Image.new(
            "RGBA",
            (
                max(1, request.target_surface.width),
                max(1, request.target_surface.height),
            ),
            (50, 50, 50, 255),
        )
    if not img2:
        img2 = Image.new(
            "RGBA",
            (
                max(1, request.target_surface.width),
                max(1, request.target_surface.height),
            ),
            (80, 80, 80, 255),
        )
    return img1, img2
