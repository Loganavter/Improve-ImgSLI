from .runtime import log_canvas_backend_choice

__all__ = ["CanvasWidget"]


def __getattr__(name):
    if name != "CanvasWidget":
        raise AttributeError(name)
    from .widget import CanvasWidget

    log_canvas_backend_choice("qrhi-widget")
    globals()["CanvasWidget"] = CanvasWidget
    return CanvasWidget
