from __future__ import annotations

import logging

from tabs.image_compare.canvas.helpers import reset_canvas_overlays

from tabs.image_compare.canvas.features.magnifier.state.mode import MagnifierModeService
from tabs.image_compare.canvas.features.magnifier.state.store import iter_magnifier_models

_log = logging.getLogger("ImproveImgSLI.magnifier.overlay")


class _StorePresenterAdapter:
    def __init__(self, store, canvas):
        self.store = store
        self.ui = _CanvasUI(canvas)

    def get_current_label_dimensions(self):
        return self.ui.image_label.width(), self.ui.image_label.height()


class _CanvasUI:
    def __init__(self, canvas):
        self.image_label = canvas


def has_visible_renderable_magnifier(store) -> bool:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return False
    if not MagnifierModeService(store).should_render_magnifiers():
        return False
    return any(
        bool(model.visible)
        for model in iter_magnifier_models(
            viewport.view_state,
            viewport.render_config,
        )
    )


def apply_magnifier_overlay(store, canvas) -> bool:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        reset_canvas_overlays(canvas)
        return False

    if not viewport.view_state.overlay_enabled:
        reset_canvas_overlays(canvas)
        return False

    has_visible = has_visible_renderable_magnifier(store)
    if not has_visible:
        reset_canvas_overlays(canvas)
        return False

    from tabs.image_compare.canvas.features.magnifier.workers.scene_update import (
        rebuild_magnifier_overlay,
    )

    rebuild_magnifier_overlay(_StorePresenterAdapter(store, canvas))
    return True


def build_magnifier_drawing_coords(
    store,
    *,
    drawing_width: int,
    drawing_height: int,
    container_width: int,
    container_height: int,
):
    if not has_visible_renderable_magnifier(store):
        return None

    from tabs.image_compare.canvas.features.magnifier.geometry.drawing_coords import get_magnifier_drawing_coords

    return get_magnifier_drawing_coords(
        store=store,
        drawing_width=drawing_width,
        drawing_height=drawing_height,
        container_width=container_width,
        container_height=container_height,
    )
