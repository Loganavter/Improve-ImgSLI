from __future__ import annotations

from core.store_viewport import RenderConfig
from domain.types import Point
from tabs.image_compare.canvas.features.magnifier.constants import (
    MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE,
)
from tabs.image_compare.canvas.features.magnifier.state.feature_state import (
    get_magnifier_widget_state,
)
from tabs.image_compare.canvas.features.magnifier.state.store import (
    DEFAULT_MAGNIFIER_ID,
    active_magnifier_id,
    add_magnifier_model,
    iter_magnifier_models,
    magnifier_enabled,
    remove_magnifier_model,
    set_active_magnifier_id,
    set_default_capture_size,
    set_default_magnifier_size,
    set_magnifier_enabled_flag,
    set_magnifier_model_visibility,
    update_magnifier_model,
)


def _state(view_state):
    return get_magnifier_widget_state(view_state)


class MagnifierStoreService:
    THRESHOLD = MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE

    def __init__(self, store):
        self.store = store

    @property
    def _view(self):
        return self.store.viewport.view_state

    @property
    def _render(self):
        viewport = getattr(self.store, "viewport", None)
        render = (
            getattr(viewport, "render_config", None) if viewport is not None else None
        )
        return render if render is not None else RenderConfig()

    def _next_magnifier_id(self) -> str:
        models = _state(self._view).models
        if DEFAULT_MAGNIFIER_ID not in models:
            return DEFAULT_MAGNIFIER_ID
        index = 2
        while f"magnifier-{index}" in models:
            index += 1
        return f"magnifier-{index}"

    def add_magnifier(
        self, magnifier_id: str | None = None, position: Point | None = None
    ):
        return add_magnifier_model(
            self._view,
            self._render,
            magnifier_id=magnifier_id or self._next_magnifier_id(),
            position=position,
        )

    def ensure_active_magnifier(self, *, create_if_missing: bool = True):
        active_id = active_magnifier_id(self._view)
        models = _state(self._view).models
        if active_id and active_id in models:
            return models[active_id]
        if len(models) == 1:
            first_id = next(iter(models.keys()))
            self.set_active_object(first_id)
            return models[first_id]
        if models:
            return None

        if create_if_missing:
            if not magnifier_enabled(self._view):
                return None
            return self.add_magnifier(DEFAULT_MAGNIFIER_ID, Point(0.5, 0.5))
        return None

    def get_active_magnifier(self):
        return self.ensure_active_magnifier(create_if_missing=False)

    def iter_magnifiers(self):
        return iter_magnifier_models(self._view, self._render)

    def get_magnifier(self, magnifier_id: str | None):
        if not magnifier_id:
            return None
        models = _state(self._view).models
        return models.get(magnifier_id)

    def count_magnifiers(self) -> int:
        return len(_state(self._view).models)

    def count_visible_magnifiers(self) -> int:
        return sum(
            1
            for model in _state(self._view).models.values()
            if model is not None and bool(model.visible)
        )

    def are_all_magnifiers_frozen(self) -> bool:
        models = [
            model for model in _state(self._view).models.values() if model is not None
        ]
        return bool(models) and all(bool(model.freeze) for model in models)

    def get_next_magnifier_id(
        self,
        current_id: str | None,
        *,
        prefer_visible: bool = True,
        include_hidden: bool = True,
    ) -> str | None:
        models = self.iter_magnifiers()
        if not models:
            return None
        ids = [model.id for model in models]
        try:
            start_index = ids.index(current_id) if current_id in ids else -1
        except ValueError:
            start_index = -1

        def _matches(model) -> bool:
            if prefer_visible and bool(getattr(model, "visible", False)):
                return True
            if include_hidden:
                return True
            return False

        total = len(models)
        for step in range(1, total + 1):
            model = models[(start_index + step) % total]
            if model.id == current_id:
                continue
            if _matches(model):
                return model.id
        return None

    def get_active_or_first_magnifier(self):
        model = self.get_active_magnifier()
        if model is not None:
            return model
        models = self.iter_magnifiers()
        return models[0] if models else None

    def remove_object(self, object_id: str) -> None:
        remove_magnifier_model(self._view, self._render, object_id)

    def set_active_object(self, object_id: str | None) -> None:
        set_active_magnifier_id(self._view, object_id)

    def set_object_visibility(self, object_id: str | None, visible: bool):
        return set_magnifier_model_visibility(
            self._view, self._render, object_id, visible
        )

    def reveal_object(self, object_id: str | None):
        model = self.set_object_visibility(object_id, True)
        if model is not None:
            set_magnifier_enabled_flag(self._view, True)
        return model

    def move_object_source_position(self, object_id: str | None, position: Point):
        target_id = object_id or active_magnifier_id(self._view) or DEFAULT_MAGNIFIER_ID
        return update_magnifier_model(
            self._view,
            self._render,
            target_id,
            position=position,
        )

    def set_object_internal_split(self, object_id: str | None, value: float):
        target_id = object_id or active_magnifier_id(self._view) or DEFAULT_MAGNIFIER_ID
        return update_magnifier_model(
            self._view,
            self._render,
            target_id,
            internal_split=max(0.0, min(1.0, float(value))),
        )

    def set_magnifier_enabled(self, enabled: bool):
        set_magnifier_enabled_flag(self._view, enabled)
        model = self.ensure_active_magnifier(create_if_missing=enabled)
        if model is not None:
            update_magnifier_model(
                self._view,
                self._render,
                model.id,
                visible=bool(enabled),
            )
        return model

    def hide_active_magnifier(self):
        active = self.get_active_or_first_magnifier()
        if active is None:
            return None
        self.set_object_visibility(active.id, False)
        self.set_active_object(active.id)
        set_magnifier_enabled_flag(self._view, True)
        return active.id

    def set_active_magnifier_size(self, size: float):
        model = self.ensure_active_magnifier()
        if model is None:
            return None
        set_default_magnifier_size(self._view, size)
        return update_magnifier_model(
            self._view,
            self._render,
            model.id,
            size_relative=float(size),
        )

    def set_active_capture_size(self, size: float):
        model = self.ensure_active_magnifier()
        if model is None:
            return None
        set_default_capture_size(self._view, size)
        return update_magnifier_model(
            self._view,
            self._render,
            model.id,
            capture_size_relative=float(size),
        )

    def set_active_magnifier_orientation(self, is_horizontal: bool):
        model = self.ensure_active_magnifier()
        if model is None:
            return None
        return update_magnifier_model(
            self._view,
            self._render,
            model.id,
            is_horizontal=bool(is_horizontal),
        )

    def set_active_magnifier_visibility_parts(
        self,
        *,
        left: bool | None = None,
        center: bool | None = None,
        right: bool | None = None,
    ):
        model = self.ensure_active_magnifier()
        if model is None:
            return None
        updates = {}
        if left is not None:
            updates["visible_left"] = bool(left)
        if center is not None:
            updates["visible_center"] = bool(center)
        if right is not None:
            updates["visible_right"] = bool(right)
        if not updates:
            return model
        return update_magnifier_model(
            self._view,
            self._render,
            model.id,
            **updates,
        )

    def set_active_magnifier_freeze(
        self,
        freeze: bool,
        *,
        frozen_position: Point | None = None,
        new_offset: Point | None = None,
    ):
        model = self.ensure_active_magnifier()
        if model is None:
            return None
        updates = {
            "freeze": bool(freeze),
            "frozen_position": frozen_position if freeze else None,
        }
        if new_offset is not None:
            updates["offset_relative"] = new_offset
        return update_magnifier_model(
            self._view,
            self._render,
            model.id,
            **updates,
        )

    def set_all_magnifiers_freeze(
        self,
        freeze: bool,
        *,
        frozen_positions: dict[str, Point] | None = None,
        new_offsets: dict[str, Point | None] | None = None,
    ) -> None:
        models = list(_state(self._view).models.values())
        for model in models:
            if model is None:
                continue
            updates = {
                "freeze": bool(freeze),
                "frozen_position": (
                    (frozen_positions or {}).get(model.id) if freeze else None
                ),
            }
            if new_offsets is not None and model.id in new_offsets:
                offset = new_offsets.get(model.id)
                if offset is not None:
                    updates["offset_relative"] = offset
            update_magnifier_model(
                self._view,
                self._render,
                model.id,
                **updates,
            )

    def set_active_magnifier_offset(self, offset: Point):
        model = self.ensure_active_magnifier()
        if model is None:
            return None
        return update_magnifier_model(
            self._view,
            self._render,
            model.id,
            offset_relative=offset,
        )

    def set_active_magnifier_spacing(self, spacing: float):
        model = self.ensure_active_magnifier()
        if model is None:
            return None
        return update_magnifier_model(
            self._view,
            self._render,
            model.id,
            spacing_relative=float(spacing),
        )

    def update_active_magnifier_combined_state(self):
        model = self.ensure_active_magnifier(create_if_missing=False)
        if model is None or not magnifier_enabled(self._view):
            return False
        return (
            bool(model.visible_left)
            and bool(model.visible_right)
            and float(model.spacing_relative) <= self.THRESHOLD + 1e-5
        )

    def is_active_magnifier_combined(self) -> bool:
        model = self.get_active_or_first_magnifier()
        if model is None or not magnifier_enabled(self._view):
            return False
        interaction = getattr(self.store.viewport, "interaction_state", None)
        use_visual = (
            interaction is not None
            and bool(getattr(interaction, "is_interactive_mode", False))
            and bool(getattr(self._view, "optimize_interactive_movement", True))
        )
        effective_spacing = (
            float(
                getattr(
                    interaction,
                    "interactive_spacing_relative_visual",
                    model.spacing_relative,
                )
            )
            if use_visual
            else float(model.spacing_relative)
        )
        return (
            bool(model.visible_left)
            and bool(model.visible_right)
            and effective_spacing <= self.THRESHOLD + 1e-5
        )

    def get_active_source_position(self) -> Point:
        model = self.get_active_or_first_magnifier()
        return model.position if model is not None else Point(0.5, 0.5)

    def get_active_offset(self) -> Point:
        model = self.get_active_or_first_magnifier()
        return model.offset_relative if model is not None else Point(0.0, 0.0)

    def get_active_spacing(self) -> float:
        model = self.get_active_or_first_magnifier()
        return float(model.spacing_relative) if model is not None else 0.0

    def get_active_frozen_position(self) -> Point | None:
        model = self.get_active_or_first_magnifier()
        return model.frozen_position if model is not None else None
