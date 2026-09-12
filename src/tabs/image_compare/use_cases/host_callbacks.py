"""Small host-facing probes/setters ``ImageCompareTab`` exposes to the
presenter layer (focus clearing, combo/button state sync, canvas-content
readiness) -- split out to keep that class down to the ``TabContract``
surface itself.
"""

from __future__ import annotations


def canvas_label(tab):
    if tab._widget is None:
        return None
    return tab._widget.image_label


def clear_transient_text_focus(tab, focused_widget) -> bool:
    if tab._widget is None:
        return False
    if focused_widget in (tab._widget.edit_name1, tab._widget.edit_name2):
        focused_widget.clearFocus()
        return True
    return False


def sync_interpolation_combo_state(
    tab, count: int, current_index: int, text: str, items: list[str]
) -> bool:
    if tab._widget is None:
        return False
    tab._widget.combo_interpolation.updateState(
        count=count, current_index=current_index, text=text, items=items
    )
    return True


def setup_view_mode_buttons(
    tab,
    diff_actions: list[tuple[str, str]],
    diff_mode: str,
    channel_actions: list[tuple[str, str]],
    channel_mode: str,
) -> bool:
    if tab._widget is None:
        return False
    tab._widget.btn_diff_mode_picker.set_actions(diff_actions)
    tab._widget.btn_diff_mode_picker.set_current(diff_mode)
    tab._widget.btn_channel_mode_picker.set_actions(channel_actions)
    tab._widget.btn_channel_mode_picker.set_current(channel_mode)
    return True


def is_canvas_content_ready(tab) -> bool:
    image_label = canvas_label(tab)
    if image_label is None:
        return False

    source_ready = bool(getattr(image_label, "_source_images_ready", False))
    if source_ready:
        return True

    uploaded = getattr(image_label, "_images_uploaded", None)
    if isinstance(uploaded, (list, tuple)) and any(bool(item) for item in uploaded):
        return True

    runtime_state = getattr(image_label, "runtime_state", None)
    if runtime_state is not None:
        uploaded = getattr(runtime_state, "_images_uploaded", None)
        if isinstance(uploaded, (list, tuple)) and any(bool(item) for item in uploaded):
            return True
        background = getattr(runtime_state, "_background_pixmap", None)
        if background is not None and not background.isNull():
            return True

    stored_qimages = getattr(image_label, "_stored_qimages", None)
    if isinstance(stored_qimages, (list, tuple)):
        for image in stored_qimages:
            if image is not None and not image.isNull():
                return True

    return False
