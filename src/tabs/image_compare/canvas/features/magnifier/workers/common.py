import shiboken6 as sip

from tabs.image_compare.canvas.features.magnifier.store import MagnifierStoreService


def get_live_image_label(presenter):
    image_label = getattr(getattr(presenter, "ui", None), "image_label", None)
    if image_label is None or not sip.isValid(image_label):
        return None
    return image_label


def get_active_magnifier_model(presenter):
    return MagnifierStoreService(presenter.store).ensure_active_magnifier(
        create_if_missing=False
    )


def start_pending_magnifier_layer(presenter) -> bool:
    pending_sig = getattr(presenter, "_pending_magnifier_signature", None)
    if pending_sig is None:
        presenter._magnifier_update_pending = False
        presenter._pending_magnifier_request_seq = 0
        presenter._pending_magnifier_requested_at = 0.0
        return False

    presenter._magnifier_update_pending = False
    presenter._pending_magnifier_signature = None
    presenter._pending_magnifier_request_seq = 0
    presenter._pending_magnifier_requested_at = 0.0
    presenter._last_mag_signature = None

    from .worker_flow import render_magnifier_layer

    return render_magnifier_layer(presenter, pending_sig)


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
