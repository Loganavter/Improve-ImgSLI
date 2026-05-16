from __future__ import annotations

from PIL import Image

def prepare_scene_images(scene_images_cache: dict, render_context, canvas_plan):
    aligned_source1 = render_context.source_image1
    aligned_source2 = render_context.source_image2
    export_size = (
        getattr(render_context.image1, "size", None),
        getattr(render_context.image2, "size", None),
    )
    source_size = (
        getattr(aligned_source1, "size", None),
        getattr(aligned_source2, "size", None),
    )
    if source_size != export_size:
        aligned_source1 = render_context.image1
        aligned_source2 = render_context.image2
    cache_key = (
        render_context.source_key,
        id(render_context.image1) if render_context.image1 is not None else 0,
        id(render_context.image2) if render_context.image2 is not None else 0,
        id(aligned_source1) if aligned_source1 is not None else 0,
        id(aligned_source2) if aligned_source2 is not None else 0,
        id(render_context.cached_diff_image) if render_context.cached_diff_image is not None else 0,
        int(canvas_plan.canvas_width),
        int(canvas_plan.canvas_height),
        int(canvas_plan.padding_left),
        int(canvas_plan.padding_top),
    )
    cached = scene_images_cache.get(cache_key)
    if cached is not None:
        return cached

    bg1, bg2 = render_context.prepared_background_layers or (
        render_context.image1,
        render_context.image2,
    )
    diff_image = render_context.cached_diff_image

    canvas_w = canvas_plan.canvas_width
    canvas_h = canvas_plan.canvas_height
    pad_left = canvas_plan.padding_left
    pad_top = canvas_plan.padding_top

    def pad(image: Image.Image | None):
        if image is None:
            return None
        result = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        result.paste(image.convert("RGBA"), (pad_left, pad_top))
        return result

    scene_images = {
        "bg1": pad(bg1),
        "bg2": pad(bg2),
        "src1": pad(aligned_source1),
        "src2": pad(aligned_source2),
        "diff": pad(diff_image) if diff_image is not None else None,
    }
    if len(scene_images_cache) >= 8:
        scene_images_cache.clear()
    scene_images_cache[cache_key] = scene_images
    return scene_images

