def compute_export_stroke_scales(
    viewport_state: dict | None, width: int, height: int
) -> tuple[float, float, float]:
    if not viewport_state:
        return 1.0, 1.0, 1.0
    display_w = max(1, int(viewport_state.get("pixmap_width", 0) or 0))
    display_h = max(1, int(viewport_state.get("pixmap_height", 0) or 0))
    scale_x = float(width) / float(display_w) if display_w > 0 else 1.0
    scale_y = float(height) / float(display_h) if display_h > 0 else 1.0
    return scale_x, scale_y, min(scale_x, scale_y)
