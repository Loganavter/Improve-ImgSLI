from .runtime import log_canvas_backend_choice

__all__ = ["GLCanvas"]


def __getattr__(name):
    if name != "GLCanvas":
        raise AttributeError(name)
    from .widget import GLCanvas

    log_canvas_backend_choice("qrhi-widget")
    globals()["GLCanvas"] = GLCanvas
    return GLCanvas
