from tabs.host_helpers import get_overlay_layer
from tabs.image_compare.canvas.registry import registry
from sli_ui_toolkit.managers import scaled_px

def _query_overlay_orientation(store) -> bool:
    query = registry().get_feature_command_by_alias("overlay.is_horizontal")
    if query is None:
        return False
    try:
        return bool(query(store))
    except AttributeError:
        return False

def on_interpolation_combo_clicked(presenter):
    if presenter.ui_manager:
        presenter.ui_manager.transient.toggle_interpolation_flyout()

def on_orientation_right_clicked(presenter):
    current_mode = getattr(presenter.store.settings, "ui_mode", "beginner")
    if current_mode == "advanced":
        _show_orientation_popup(presenter)
        return
    if current_mode != "expert":
        return
    binding = registry().get_feature_toolbar_binding("divider.orientation")
    if binding is not None and binding.on_right_clicked is not None:
        binding.on_right_clicked(presenter)

def _orientation_popup_size():
    """Design px for the orientation quick-switch badge, resolved at use time.

    The app ``OverlayLayer.show_popup(size=...)`` channel copies ``size``
    verbatim into ``setFixedSize`` (measured at 1.0/1.5: the box does not
    scale), so the caller owns the conversion. Built first and passed as a
    plain ``QSize`` because an inline ``scaled_px`` inside a ``size=`` kwarg is
    the double-scaling trap the raw-px contract gate flags.
    """
    from PySide6.QtCore import QSize

    return QSize(scaled_px(32), scaled_px(28))


def _show_orientation_popup(presenter):
    from tabs.image_compare.icons import Icon, get_icon

    current_orientation = _query_overlay_orientation(presenter.store)
    icon_enum = (
        Icon.HORIZONTAL_SPLIT
        if not current_orientation
        else Icon.VERTICAL_SPLIT
    )
    widget = getattr(presenter, "widget", None)
    button = getattr(widget, "btn_orientation", None)
    if button is None:
        return
    overlay_layer = get_overlay_layer(button)
    if overlay_layer is None:
        return

    overlay_layer.show_popup(
        "orientation_popup",
        button,
        pixmap=get_icon(icon_enum).pixmap(18, 18),
        size=_orientation_popup_size(),
        position="top",
        offset=6,
        timeout_ms=800,
    )
