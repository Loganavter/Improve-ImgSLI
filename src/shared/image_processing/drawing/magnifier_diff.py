from PIL import Image

def create_diff_image(
    drawer,
    image1: Image.Image,
    image2: Image.Image | None,
    mode: str = "highlight",
    threshold: int = 20,
    font_path: str | None = None,
) -> Image.Image | None:
    return drawer._create_diff_image(
        image1=image1,
        image2=image2,
        mode=mode,
        threshold=threshold,
        font_path=font_path,
    )

def get_magnifier_content_size(magnifier_size: int) -> int:
    border_width = max(2, int(magnifier_size * 0.015))
    content_size = magnifier_size - border_width * 2 + 2
    return max(1, content_size)

def build_diff_patch(
    drawer,
    *,
    store,
    diff_mode: str,
    magnifier_size: int,
    image1_for_crop: Image.Image,
    image2_for_crop: Image.Image,
    crop_box1: tuple,
    crop_box2: tuple,
    interpolation_method: str,
    is_interactive: bool,
    font_path: str | None = None,
) -> Image.Image | None:
    cached_map = getattr(store.viewport.session_data.render_cache, "cached_diff_image", None)
    content_size = get_magnifier_content_size(magnifier_size)
    if cached_map:
        diff_patch = drawer._get_normalized_content(
            cached_map,
            crop_box1,
            content_size,
            interpolation_method,
            is_interactive,
        )
        if diff_patch is not None:
            return diff_patch

    analysis_interp = "BILINEAR"
    norm1 = drawer._get_normalized_content(
        image1_for_crop,
        crop_box1,
        content_size,
        analysis_interp,
        is_interactive,
    )
    norm2 = None
    if diff_mode != "edges":
        norm2 = drawer._get_normalized_content(
            image2_for_crop,
            crop_box2,
            content_size,
            analysis_interp,
            is_interactive,
        )
    return create_diff_image(
        drawer,
        norm1,
        None if diff_mode == "edges" else norm2,
        mode=diff_mode,
        font_path=font_path,
    )

def build_optional_diff_patch(
    drawer,
    *,
    show_center: bool,
    store,
    diff_mode: str,
    magnifier_size: int,
    image1_for_crop: Image.Image,
    image2_for_crop: Image.Image,
    crop_box1: tuple,
    crop_box2: tuple,
    interpolation_method: str,
    is_interactive: bool,
    font_path: str | None,
) -> Image.Image | None:
    if not show_center:
        return None
    return build_diff_patch(
        drawer,
        store=store,
        diff_mode=diff_mode,
        magnifier_size=magnifier_size,
        image1_for_crop=image1_for_crop,
        image2_for_crop=image2_for_crop,
        crop_box1=crop_box1,
        crop_box2=crop_box2,
        interpolation_method=interpolation_method,
        is_interactive=is_interactive,
        font_path=font_path,
    )
