"""Source image loading for snapshot frames."""

from __future__ import annotations

from PIL import Image

from tabs.image_compare.plugins.video_editor.services.video_export_models import (
    VideoRenderRequest,
)


def resolve_images(image_loader, snap, request: VideoRenderRequest, *, get_crop_service=None):
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

    # W3c: snapshots render the crop windows (black borders excluded),
    # sourced from the full-frame loader outputs. Getter unset (all export
    # still paths, which pass auto_crop=False) → boxes None → identical.
    if get_crop_service is not None:
        try:
            from tabs.image_compare.services.analysis.analysis_pair import (
                crop_pair_to_boxes,
                resolve_crop_boxes_for_paths,
            )

            box1, box2 = resolve_crop_boxes_for_paths(
                getattr(snap, "image1_path", None),
                getattr(snap, "image2_path", None),
                get_crop_service,
            )
            img1, img2 = crop_pair_to_boxes(img1, img2, box1, box2)
        except Exception:
            pass
    return img1, img2