import logging
from PySide6.QtCore import QSignalBlocker
from sli_ui_toolkit.i18n import tr
from tabs.image_compare.canvas.registry import registry
from ui.canvas_infra.viewport.state import get_zoom_level
from tabs.image_compare.icons import Icon

logger = logging.getLogger("ImproveImgSLI")

_TOOLBAR_CONTROL_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("btn_orientation", ("divider.orientation",)),
    ("btn_orientation_simple", ("divider.orientation_simple",)),
    ("btn_divider_visible", ("divider.visible",)),
    ("btn_divider_color", ("divider.color",)),
    ("btn_divider_width", ("divider.width",)),
    ("btn_magnifier", ("magnifier.enabled",)),
    ("btn_magnifier_orientation", ("magnifier.orientation", "magnifier.divider.thickness")),
    ("btn_magnifier_orientation_simple", ("magnifier.orientation",)),
    ("btn_magnifier_divider_visible", ("magnifier.divider.visibility",)),
    ("btn_magnifier_divider_width", ("magnifier.divider.thickness",)),
    ("btn_magnifier_instances", ("magnifier.instances.add", "magnifier.instances.remove")),
    ("btn_freeze", ("magnifier.freeze",)),
    ("slider_size", ("magnifier.size",)),
    ("slider_capture", ("capture.size",)),
    ("btn_file_names", ("filename_overlay.visible",)),
    ("btn_magnifier_guides_simple", ("guides.enabled_simple",)),
    ("btn_magnifier_guides_width", ("guides.thickness",)),
)

def _set_slider_value_quietly(slider, value: int) -> None:
    if slider.value() == value:
        return
    blocker = QSignalBlocker(slider)
    try:
        slider.setValue(value)
    finally:
        del blocker

# Last logged deleted-control attr (throttle: one debug line per attr, not
# per store emit — the sync fanout runs on every emit and a dead wrapper
# would otherwise spam once per emit until the next widget rebuild).
_last_dead_control_log_sig = None  # type: ignore


def _is_qt_alive(control) -> bool:
    """False when a PySide6 wrapper outlived its C++ object.

    Same guard as ui_update_batcher._flush_updates: chrome rebuilds between
    store emits can delete the C++ side while the Python attr on the widget
    still references the wrapper (hasattr passes, any C++ call raises
    RuntimeError). Fail-open True when shiboken is unavailable or undecided —
    the per-control try/except RuntimeError below still catches it.
    """
    try:
        import shiboken6  # type: ignore
    except Exception:
        return True
    try:
        return bool(shiboken6.isValid(control))
    except Exception:
        return True


def _note_dead_control(attr_name: str) -> None:
    global _last_dead_control_log_sig
    if _last_dead_control_log_sig != attr_name:
        _last_dead_control_log_sig = attr_name
        logger.debug("toolbar availability: skip deleted control %s", attr_name)

def check_name_lengths(presenter):
    len1 = len(presenter.widget.edit_name1.text().strip())
    len2 = len(presenter.widget.edit_name2.text().strip())
    limit = presenter.store.viewport.render_config.max_name_length
    if (
        len1 > limit or len2 > limit
    ) and presenter.store.viewport.render_config.include_file_names_in_saved:
        warning = tr(
            "image_compare.misc.name_length_limit_exceeded",
            presenter.store.settings.current_language,
            limit=limit,
        )
        presenter.widget.update_name_length_warning(warning, "", True)
    else:
        presenter.widget.update_name_length_warning("", "", False)

def _update_canvas_feature_control_availability(presenter) -> None:
    widget = getattr(presenter, "widget", None)
    if widget is None:
        return
    for attr_name, control_ids in _TOOLBAR_CONTROL_GROUPS:
        control = getattr(widget, attr_name, None)
        if control is None or not hasattr(control, "setEnabled"):
            continue
        if not _is_qt_alive(control):
            _note_dead_control(attr_name)
            continue
        try:
            control.setEnabled(
                any(registry().get_feature_toolbar_binding(control_id) is not None for control_id in control_ids)
            )
        except RuntimeError:
            # Wrapper outlived its C++ object (chrome rebuild between emits):
            # skip this control, keep syncing the rest. The stale attr
            # refreshes on the next widget rebuild.
            _note_dead_control(attr_name)
            continue

def update_toolbar_states(presenter):
    file_names_btn = getattr(presenter.widget, "btn_file_names", None)
    if file_names_btn is None or not _is_qt_alive(file_names_btn):
        if file_names_btn is not None:
            _note_dead_control("btn_file_names")
    else:
        file_names_btn.setChecked(
            presenter.store.viewport.render_config.include_file_names_in_saved, emit_signal=False
        )
        image_label = getattr(presenter.widget, "image_label", None)
        zoom_level = get_zoom_level(image_label) if image_label is not None else 1.0
        file_names_temporarily_hidden = (
            presenter.store.viewport.render_config.include_file_names_in_saved and abs(zoom_level - 1.0) > 1e-6
        )
        if hasattr(file_names_btn, "setVisualIconOverride"):
            file_names_btn.setVisualIconOverride(
                Icon.DIVIDER_HIDDEN if file_names_temporarily_hidden else None
            )
        lang = presenter.store.settings.current_language
        file_names_btn.setToolTip(
            tr("tooltip.file_names_hidden_on_zoom", lang)
            if file_names_temporarily_hidden
            else tr("image_compare.ui.include_file_names_in_saved_image", lang)
        )
    _update_canvas_feature_control_availability(presenter)
    speed_slider = getattr(presenter.widget, "slider_speed", None)
    if speed_slider is None or not _is_qt_alive(speed_slider):
        if speed_slider is not None:
            _note_dead_control("slider_speed")
    else:
        try:
            _set_slider_value_quietly(
                speed_slider,
                int(presenter.store.viewport.view_state.movement_speed_per_sec * 100),
            )
        except RuntimeError:
            _note_dead_control("slider_speed")
    for binding in registry().get_feature_toolbar_bindings():
        if binding.sync_state is not None:
            try:
                binding.sync_state(presenter)
            except RuntimeError:
                # One feature's stale widget refs must not take down the
                # whole fanout (capture/widget.py ValueSlider storm).
                logger.debug(
                    "toolbar sync_state skipped (deleted): %s",
                    getattr(binding, "control_id", "?"),
                )

def on_color_option_clicked(presenter, option: str):
    settings_presenter = _get_settings_presenter_from_window(presenter)
    if settings_presenter is None:
        logger.warning("ToolbarPresenter: settings_presenter not found")
        return

    if option == "divider":
        settings_presenter.show_magnifier_divider_color_picker()
    elif option == "capture":
        settings_presenter.show_capture_ring_color_picker()
    elif option == "border":
        settings_presenter.show_magnifier_border_color_picker()
    elif option == "laser":
        settings_presenter.show_laser_color_picker()

def _get_window_presenter(presenter):
    return getattr(presenter.main_window_app, "presenter", None)

def _get_settings_presenter_from_window(presenter):
    window_presenter = _get_window_presenter(presenter)
    if window_presenter is not None and hasattr(window_presenter, "get_feature"):
        return window_presenter.get_feature("settings")
    return None
