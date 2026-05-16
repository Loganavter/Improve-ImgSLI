from dataclasses import dataclass

from ui.widgets.gl_canvas.style_tokens import DEFAULT_CANVAS_STYLE_TOKENS

@dataclass(frozen=True)
class GLFilenameOverlayConfig:
    enabled: bool = False
    image_display_rect: tuple[int, int, int, int] | None = None
    text_placement_mode: str = "edges"
    split_position: float = 0.5
    is_horizontal: bool = False
    divider_thickness: int = 0
    is_interactive_mode: bool = False
    draw_text_background: bool = True
    font_base_pixel_size: float = DEFAULT_CANVAS_STYLE_TOKENS.filename_font_base_du
    font_size_percent: int = 100
    font_weight: int = 0
    text_alpha_percent: int = 100
    file_name_color: object | None = None
    file_name_bg_color: object | None = None
    max_name_length: int = 50
    name1: str = ""
    name2: str = ""
