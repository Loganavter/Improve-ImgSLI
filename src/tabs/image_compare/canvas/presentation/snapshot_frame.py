from __future__ import annotations

from PIL import Image

from shared.image_processing.pixel_ops.downscale import downscale_source_to_pil
from ui.canvas_presentation.layout import compute_content_layout
from ui.canvas_presentation.models import (
    CanvasTarget,
    RenderFramePresentation,
    SnapshotStorePresentation,
)

def build_render_frame_presentation(
    presentation: SnapshotStorePresentation,
    *,
    output_width: int | None = None,
    output_height: int | None = None,
    target: CanvasTarget | None = None,
) -> RenderFramePresentation:
    display_img1 = presentation.display_image1
    display_img2 = presentation.display_image2
    if display_img1 is None or display_img2 is None:
        raise ValueError("Render frame presentation requires both display images.")

    resolved_target = target or CanvasTarget(
        width=max(1, int(output_width or 1)),
        height=max(1, int(output_height or 1)),
        fill_rgba=presentation.fill_rgba,
    )
    layout = compute_content_layout(
        resolved_target,
        image_width=display_img1.width,
        image_height=display_img1.height,
    )
    render_w = layout.content_width
    render_h = layout.content_height
    image_dest_x = layout.content_x
    image_dest_y = layout.content_y

    presentation.store.viewport.geometry_state.pixmap_width = render_w
    presentation.store.viewport.geometry_state.pixmap_height = render_h

    scaled_image1 = downscale_source_to_pil(
        display_img1, (render_w, render_h), resample=Image.Resampling.BILINEAR
    )
    scaled_image2 = downscale_source_to_pil(
        display_img2, (render_w, render_h), resample=Image.Resampling.BILINEAR
    )

    return RenderFramePresentation(
        store=presentation.store,
        images=presentation.images,
        target=resolved_target,
        layout=layout,
        render_width=render_w,
        render_height=render_h,
        image_dest_x=image_dest_x,
        image_dest_y=image_dest_y,
        scaled_image1=scaled_image1,
        scaled_image2=scaled_image2,
        virtual_layout=presentation.virtual_layout,
    )

