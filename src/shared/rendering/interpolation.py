from __future__ import annotations

def get_effective_main_interpolation_method(vp) -> str:
    """Return the active interpolation method from viewport render_config.

    Reads only vp.render_config — no feature-specific state.
    """
    viewport_value = getattr(vp.render_config, "interpolation_method", None)
    if viewport_value:
        return viewport_value
    render_cfg = getattr(vp, "render_config", None)
    return (
        getattr(render_cfg, "interpolation_method", "BILINEAR")
        if render_cfg
        else "BILINEAR"
    )

def get_effective_export_interpolation_method(vp) -> str:
    method = str(get_effective_main_interpolation_method(vp) or "LANCZOS").upper()
    if method == "NEAREST":
        return "LANCZOS"
    return method
