from __future__ import annotations

# File-Size-Exempt: flat per-field viewport setters sharing one guard/emit
# shape — splitting by field (size/offset/color/...) creates grab-bag
# modules threading the same store/viewport/render_config triple.

from typing import Any

from domain.types import Point


def viewport_toggle_enabled(store, enabled: bool):
    from tabs.image_compare.canvas.features.magnifier.state.mode import MagnifierModeService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    return MagnifierModeService(store).toggle_from_button(bool(enabled))


def viewport_ensure_active(store):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    return MagnifierStoreService(store).ensure_active_magnifier()


def viewport_set_active_size(store, size: float):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_size(float(size))
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_capture_size(store, size: float):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_capture_size(float(size))
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_offset(store, offset):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_offset(offset)
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_spacing(store, spacing: float):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_spacing(float(spacing))
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_border_color(store, color):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService
    from tabs.image_compare.canvas.features.magnifier.state.store import update_magnifier_model

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    result = update_magnifier_model(
        store.viewport.view_state,
        store.viewport.render_config,
        model.id,
        border_color=color,
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_divider_color(store, color):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService
    from tabs.image_compare.canvas.features.magnifier.state.store import update_magnifier_model

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    result = update_magnifier_model(
        store.viewport.view_state,
        store.viewport.render_config,
        model.id,
        divider_color=color,
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_guides_color(store, color):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService
    from tabs.image_compare.canvas.features.magnifier.state.store import update_magnifier_model

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    result = update_magnifier_model(
        store.viewport.view_state,
        store.viewport.render_config,
        model.id,
        guides_color=color,
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_laser_enabled(store, enabled: bool):
    if not bool(enabled):
        try:
            import logging
            import traceback

            from shared.debug_flags import env_flag as _env_flag

            _lg = logging.getLogger("ImproveImgSLI")
            if _env_flag("IMGSLI_LASER_DEBUG"):
                prefix = "[laser-debug]"
                stack = "".join(traceback.format_stack(limit=15)[:-1])
                if _env_flag("IMGSLI_LASER_DEBUG"):
                    _lg.warning("%s LASER DISABLE [viewport_set_active_laser_enabled(enabled=False)]\n%s", prefix, stack)
                else:
                    _lg.debug("%s LASER DISABLE [viewport_set_active_laser_enabled(enabled=False)]\n%s", prefix, stack)
        except Exception:
            pass
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService
    from tabs.image_compare.canvas.features.magnifier.state.store import update_magnifier_model

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    result = update_magnifier_model(
        store.viewport.view_state,
        store.viewport.render_config,
        model.id,
        show_laser=bool(enabled),
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_visibility_parts(
    store,
    *,
    left: bool | None = None,
    center: bool | None = None,
    right: bool | None = None,
):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_visibility_parts(
        left=left,
        center=center,
        right=right,
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_orientation(store, is_horizontal: bool):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_magnifier_orientation(
        bool(is_horizontal)
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_move_active_position(store, position):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService
    from tabs.image_compare.canvas.features.magnifier.state.store import active_magnifier_id

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).move_object_source_position(
        active_magnifier_id(store.viewport.view_state),
        position,
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_internal_split(store, location):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_magnifier()
    if model is None:
        return None
    value = 0.5
    if isinstance(location, Point):
        value = location.x if not model.is_horizontal else location.y
    elif isinstance(location, (float, int)):
        value = float(location)
    value = max(0.0, min(1.0, value))
    if model.internal_split == value:
        return model
    result = scene_state.set_object_internal_split(model.id, value)
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_add_instance(store, position=None):
    from domain.types import Point

    from tabs.image_compare.canvas.features.magnifier.state.mode import MagnifierModeService
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    def _dbg(msg, *args):
        try:
            from tabs.image_compare.debug import ic_magnifier_debug

            ic_magnifier_debug(msg, *args)
        except Exception:
            pass

    def _trace(summary, payload):
        try:
            from core.tracing.tracer import Tracer

            if Tracer.enabled():
                Tracer.instance().record("magnifier.instances.added", summary, payload)
        except Exception:
            pass

    if store is None or getattr(store, "viewport", None) is None:
        _dbg("add_instance: no store/viewport")
        return None
    try:
        before = len(list(MagnifierStoreService(store).iter_magnifiers()))
    except Exception:
        before = -1
    _dbg("add_instance: enter count_before=%s", before)
    MagnifierModeService(store).prepare_for_add()

    if position is None:
        existing = list(MagnifierStoreService(store).iter_magnifiers())
        if existing:

            first = existing[0]
            offset_x = 0.08 if first.position.x < 0.5 else -0.08
            offset_y = 0.08 if first.position.y < 0.5 else -0.08
            position = Point(
                max(0.1, min(0.9, first.position.x + offset_x)),
                max(0.1, min(0.9, first.position.y + offset_y)),
            )

    model = MagnifierStoreService(store).add_magnifier(position=position)
    try:
        after = len(list(MagnifierStoreService(store).iter_magnifiers()))
    except Exception:
        after = -1
    _dbg("add_instance: exit count_before=%s count_after=%s emit=viewport", before, after)
    _trace("instances added", {"count_before": before, "count_after": after})
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return model


def viewport_remove_active_instance(store) -> bool:
    from tabs.image_compare.canvas.features.magnifier.state.mode import MagnifierModeService
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService
    from tabs.image_compare.canvas.features.magnifier.state.store import active_magnifier_id

    def _dbg(msg, *args):
        try:
            from tabs.image_compare.debug import ic_magnifier_debug

            ic_magnifier_debug(msg, *args)
        except Exception:
            pass

    def _trace(summary, payload):
        try:
            from core.tracing.tracer import Tracer

            if Tracer.enabled():
                Tracer.instance().record("magnifier.instances.removed", summary, payload)
        except Exception:
            pass

    if store is None or getattr(store, "viewport", None) is None:
        _dbg("remove_instance: no store/viewport -> False")
        return False
    scene_state = MagnifierStoreService(store)
    try:
        before = len(list(scene_state.iter_magnifiers()))
    except Exception:
        before = -1
    if len(scene_state.iter_magnifiers()) <= 1:
        _dbg("remove_instance: reject count_before=%s (need >1)", before)
        _trace("remove rejected", {"count_before": before, "reason": "single"})
        return False
    active = active_magnifier_id(store.viewport.view_state)
    if not active:
        _dbg("remove_instance: reject count_before=%s reason=no_active", before)
        _trace("remove rejected", {"count_before": before, "reason": "no_active"})
        return False
    scene_state.remove_object(active)
    MagnifierModeService(store).normalize_after_remove()
    try:
        after = len(list(scene_state.iter_magnifiers()))
    except Exception:
        after = -1
    _dbg("remove_instance: exit count_before=%s count_after=%s emit=none", before, after)
    _trace("instances removed", {"count_before": before, "count_after": after})

    return True


def viewport_set_active_instance(store, magnifier_id: str):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_active_object(magnifier_id)
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_instance_visibility(
    store,
    magnifier_id: str,
    visible: bool,
):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_object_visibility(
        magnifier_id,
        bool(visible),
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_all_freeze(
    store,
    freeze: bool,
    *,
    frozen_positions: dict[str, Any] | None = None,
    new_offsets: dict[str, Any] | None = None,
):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    result = MagnifierStoreService(store).set_all_magnifiers_freeze(
        bool(freeze),
        frozen_positions=frozen_positions,
        new_offsets=new_offsets,
    )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_freeze(
    store,
    freeze: bool,
):
    import math

    from domain.types import Point

    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    from tabs.image_compare.canvas.features.magnifier.state.store import update_magnifier_model

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None
    if freeze:
        result = scene_state.set_active_magnifier_freeze(
            True,
            frozen_position=model.position,
        )
    else:
        frozen = model.frozen_position
        if frozen is None:
            new_offset = None
        else:
            pix_w = int(getattr(store.viewport.geometry_state, "pixmap_width", 0) or 0)
            pix_h = int(getattr(store.viewport.geometry_state, "pixmap_height", 0) or 0)
            if pix_w > 0 and pix_h > 0:
                max_dim = math.sqrt(float(pix_w) * float(pix_h))
                dx_px = (frozen.x - model.position.x) * pix_w
                dy_px = (frozen.y - model.position.y) * pix_h
                new_offset = Point(
                    model.offset_relative.x + dx_px / max_dim,
                    model.offset_relative.y + dy_px / max_dim,
                )
            else:
                new_offset = None
        updates = {"freeze": False, "frozen_position": None}
        if new_offset is not None:
            updates["offset_relative"] = new_offset
        result = update_magnifier_model(
            store.viewport.view_state,
            store.viewport.render_config,
            model.id,
            **updates,
        )
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result


def viewport_set_active_combined(
    store,
    combined: bool,
):
    from tabs.image_compare.canvas.features.magnifier.state.service import MagnifierStoreService

    if store is None or getattr(store, "viewport", None) is None:
        return None
    scene_state = MagnifierStoreService(store)
    model = scene_state.get_active_or_first_magnifier()
    if model is None:
        return None

    if bool(combined):

        target_spacing = 0.0
    else:

        target_spacing = float(model.spacing_relative)

    result = scene_state.set_active_magnifier_spacing(target_spacing)
    if hasattr(store, "emit_viewport_change"):
        store.emit_viewport_change()
    return result
