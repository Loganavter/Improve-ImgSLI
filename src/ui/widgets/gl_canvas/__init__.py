from .runtime import (
    log_canvas_backend_choice,
    should_use_opengl_widget_canvas,
    should_use_quick_probe_canvas,
    should_use_software_canvas,
)

if should_use_quick_probe_canvas():
    from .quick_canvas import GLCanvas

    log_canvas_backend_choice("quick")
elif should_use_opengl_widget_canvas():
    from .widget import GLCanvas

    log_canvas_backend_choice("opengl-widget")
elif should_use_software_canvas():
    from .software_widget import SoftwareCanvas as GLCanvas

    log_canvas_backend_choice("software")
else:
    from .window_host import GLCanvas

    log_canvas_backend_choice("opengl-window")

__all__ = ["GLCanvas", "should_use_software_canvas"]
