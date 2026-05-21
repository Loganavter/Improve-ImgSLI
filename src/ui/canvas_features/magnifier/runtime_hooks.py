from __future__ import annotations

import logging
from typing import Any

from core.constants import AppConstants
from domain.qt_adapters import color_to_qcolor
from domain.types import Point

from .state import get_magnifier_widget_state

_log = logging.getLogger("ImproveImgSLI.magnifier")

def command_build_render_canvas_payload(store) -> dict[str, Any]:
    from .store import (
        MagnifierStoreService,
        default_capture_size,
        default_magnifier_size,
        iter_magnifier_models,
        magnifier_enabled,
    )

    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {}

    view = viewport.view_state
    render = viewport.render_config
    interaction = viewport.interaction_state
    scene_state = MagnifierStoreService(store)
    magnifier = scene_state.get_active_or_first_magnifier()
    magnifier_state = get_magnifier_widget_state(view)
    all_models = iter_magnifier_models(view, render)
    capture_areas = [
        (
            float(model.position.x),
            float(model.position.y),
            float(model.capture_size_relative),
        )
        for model in all_models
        if bool(model.visible) and bool(getattr(model, "show_capture_area", True))
    ]

    if magnifier is None:
        position = (0.5, 0.5)
        visual_offset = (0.0, 0.0)
        visual_spacing = 0.0
        size = default_magnifier_size(view)
        capture_size = default_capture_size(view)
        layout_horizontal = False
        internal_split = 0.5
        visible_left = True
        visible_center = True
        visible_right = True
        combined = False
        border_color = magnifier_state.default_border_color
        real_offset = Point(0.0, 0.0)
        real_spacing = 0.0
    else:
        position = (magnifier.position.x, magnifier.position.y)
        visual_offset = (magnifier.offset_relative.x, magnifier.offset_relative.y)
        visual_spacing = magnifier.spacing_relative
        size = magnifier.size_relative
        capture_size = magnifier.capture_size_relative
        layout_horizontal = magnifier.is_horizontal
        internal_split = magnifier.internal_split
        visible_left = magnifier.visible_left
        visible_center = magnifier.visible_center
        visible_right = magnifier.visible_right
        combined = scene_state.is_active_magnifier_combined()
        border_color = magnifier.border_color
        real_offset = magnifier.offset_relative
        real_spacing = magnifier.spacing_relative

    if magnifier_enabled(view) and interaction.is_interactive_mode:
        visual_offset = interaction.interactive_offset_relative_visual
        visual_spacing = interaction.interactive_spacing_relative_visual

    main_interp = render.interpolation_method
    optimize_movement = getattr(view, "optimize_interactive_movement", True)
    movement_interp = getattr(
        render,
        "interactive_movement_interpolation_method",
        "BILINEAR",
    )

    def resolve_interpolation(option: str) -> str:
        main_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(main_interp, 999)
        option_speed = AppConstants.INTERPOLATION_SPEED_ORDER.get(option, 999)
        return main_interp if main_speed <= option_speed else option

    effective_movement_interp = (
        resolve_interpolation(movement_interp) if optimize_movement else main_interp
    )

    is_mag_enabled = magnifier_enabled(view)
    return {
        "position": position,
        "visual_offset": visual_offset,
        "visual_spacing": visual_spacing,
        "size": size,
        "capture_size": capture_size,
        "layout_horizontal": layout_horizontal,
        "split": internal_split,
        "enabled": is_mag_enabled,
        "show_left": visible_left,
        "show_center": visible_center,
        "show_right": visible_right,
        "combined": combined,
        "border_color": (
            int(border_color.r),
            int(border_color.g),
            int(border_color.b),
            int(border_color.a),
        ),
        "capture_areas": capture_areas,
        "movement_interpolation_method": effective_movement_interp,
        "real_offset": (real_offset.x, real_offset.y),
        "real_spacing": real_spacing,
    }

def prepare_magnifier_worker_viewport(source_store, worker_viewport) -> None:
    from .store import MagnifierStoreService, update_magnifier_model

    source_scene_state = MagnifierStoreService(source_store)
    active_magnifier = source_scene_state.get_active_or_first_magnifier()
    if active_magnifier is None:
        return

    interaction = source_store.viewport.interaction_state
    cloned = active_magnifier.clone()
    if interaction.is_interactive_mode:
        cloned.offset_relative = interaction.interactive_offset_relative_visual
        cloned.spacing_relative = interaction.interactive_spacing_relative_visual
        cloned.internal_split = interaction.interactive_internal_split_visual
    update_magnifier_model(
        worker_viewport.view_state,
        worker_viewport.render_config,
        cloned.id,
        **cloned.__dict__,
    )

def build_magnifier_render_scene_overrides(store) -> dict[str, Any]:
    from .mode import MagnifierModeService
    from .store import active_or_default_border_color

    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {}
    return {
        "render_magnifiers": MagnifierModeService(store).should_render_magnifiers(),
        "border_color": color_to_qcolor(
            active_or_default_border_color(viewport.view_state)
        ),
    }
