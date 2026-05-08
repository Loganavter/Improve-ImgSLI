from .runtime import log_canvas_backend_choice

from .widget import GLCanvas

log_canvas_backend_choice("opengl-widget")

__all__ = ["GLCanvas"]
