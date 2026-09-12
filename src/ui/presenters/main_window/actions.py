from resources.translations import tr
from shared_toolkit.ui.message_dialog import AppMessageDialog
from shared_toolkit.ui.overlay_layer import get_overlay_layer


def hide_orientation_popup(presenter):
    overlay_layer = get_overlay_layer(presenter.main_window_app)
    if overlay_layer is not None:
        overlay_layer.hide_popup("orientation_popup")
    if presenter._orientation_popup:
        presenter._orientation_popup.hide()

def on_error_occurred(presenter, error_message: str):
    lang = presenter.store.settings.current_language
    AppMessageDialog.warning(
        presenter.main_window_app,
        tr("common.error", lang),
        error_message,
        ok_text=tr("common.ok", lang),
    )

def on_update_requested(presenter):
    presenter.main_window_app.schedule_update()

def on_ui_update_requested(presenter, components: list):
    presenter.ui_batcher.schedule_batch_update(components)

def start_interactive_movement(presenter):
    image_canvas = presenter.get_feature("image_canvas")
    if image_canvas is not None:
        image_canvas.start_interactive_movement()

def stop_interactive_movement(presenter):
    image_canvas = presenter.get_feature("image_canvas")
    if image_canvas is not None:
        image_canvas.stop_interactive_movement()
