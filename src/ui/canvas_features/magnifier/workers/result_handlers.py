from ui.canvas_features.magnifier import iter_magnifier_models
from ui.widgets.gl_canvas.helpers import reset_canvas_overlays

from .common import get_live_image_label

def _has_visible_magnifiers(presenter) -> bool:
    return any(
        bool(model.visible)
        for model in iter_magnifier_models(
            presenter.store.viewport.view_state,
            presenter.store.viewport.render_config,
        )
    )

def stop_interactive_movement(presenter, log_gate):
    del log_gate
    presenter.store.viewport.interaction_state.is_interactive_mode = False
    presenter._cached_split_pos = -1.0
    presenter._last_mag_signature = None
    image_label = get_live_image_label(presenter)

    if not _has_visible_magnifiers(presenter):
        if presenter.view.is_gl_canvas():
            if image_label is not None:
                reset_canvas_overlays(image_label)
        else:
            presenter.overlay.rebuild_overlay()
    else:
        presenter.overlay.rebuild_overlay()
    presenter.schedule_update()

def update_capture_area_display(presenter):
    if _has_visible_magnifiers(presenter):
        presenter.overlay.rebuild_overlay()
