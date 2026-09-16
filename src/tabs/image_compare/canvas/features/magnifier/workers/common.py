import shiboken6 as sip


def get_live_image_label(presenter):
    image_label = getattr(getattr(presenter, "widget", None), "image_label", None)
    if image_label is None or not sip.isValid(image_label):
        return None
    return image_label


def is_effective_magnifier_interactive(vp) -> bool:
    interaction = getattr(vp, "interaction_state", None)
    is_pointer_interacting = bool(
        interaction
        and (
            getattr(interaction, "is_interactive_mode", False)
            or getattr(interaction, "is_dragging_overlay_handle", False)
            or getattr(interaction, "is_dragging_overlay_split", False)
            or getattr(interaction, "is_dragging_split_line", False)
            or bool(getattr(interaction, "pressed_keys", set()))
        )
    )
    return bool(
        is_pointer_interacting
        and getattr(vp.view_state, "optimize_interactive_movement", True)
    )


def get_effective_main_interpolation_method(vp) -> str:
    viewport_value = getattr(vp.render_config, "interpolation_method", None)
    if viewport_value:
        return viewport_value
    render_cfg = getattr(vp, "render_config", None)
    return (
        getattr(render_cfg, "interpolation_method", "BILINEAR")
        if render_cfg
        else "BILINEAR"
    )
