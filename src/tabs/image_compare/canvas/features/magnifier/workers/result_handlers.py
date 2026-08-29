from tabs.image_compare.canvas.features.magnifier.state.store import iter_magnifier_models
from tabs.image_compare.canvas.helpers import reset_canvas_overlays

from tabs.image_compare.canvas.features.magnifier.workers.common import get_live_image_label


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
    try:
        _dispatcher = presenter.store.get_dispatcher() if hasattr(presenter.store, "get_dispatcher") else None
    except Exception:
        _dispatcher = None
    if _dispatcher is not None:
        try:
            from core.state_management.interaction_actions import SetInteractiveModeAction

            _dispatcher.dispatch(SetInteractiveModeAction(False), scope="viewport.interaction")
        except Exception:
            setattr(presenter.store.viewport.interaction_state, "is_interactive_mode", False)
            if hasattr(presenter.store, "emit_viewport_change"):
                presenter.store.emit_viewport_change("interaction")
    else:
        setattr(presenter.store.viewport.interaction_state, "is_interactive_mode", False)
        if hasattr(presenter.store, "emit_viewport_change"):
            presenter.store.emit_viewport_change("interaction")
    presenter._cached_split_pos = -1.0
    presenter._last_mag_signature = None
    image_label = get_live_image_label(presenter)

    if not _has_visible_magnifiers(presenter):
        if presenter.view.is_canvas_widget():
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
