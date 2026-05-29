from __future__ import annotations

from .store import (
    default_capture_size,
    default_magnifier_size,
    iter_magnifier_models,
    magnifier_enabled,
    set_magnifier_enabled_flag,
)
from .store import MagnifierStoreService

class MagnifierModeService:
    def __init__(self, store):
        self.store = store
        self.object_state = MagnifierStoreService(store)

    @property
    def _view(self):
        return self.store.viewport.view_state

    @property
    def _render(self):
        return self.store.viewport.render_config

    def iter_magnifiers(self):
        return iter_magnifier_models(self._view, self._render)

    def total_count(self) -> int:
        return len(self.iter_magnifiers())

    def visible_count(self) -> int:
        return sum(1 for model in self.iter_magnifiers() if bool(getattr(model, "visible", False)))

    def is_multi_mode(self) -> bool:
        return self.total_count() > 1

    def should_show_panel(self) -> bool:
        total = self.total_count()
        if total > 1:
            return True
        if total == 1:
            return bool(magnifier_enabled(self._view))
        return False

    def should_render_magnifiers(self) -> bool:
        return bool(magnifier_enabled(self._view))

    def resolve_button_checked(self, active_model) -> bool:
        if self.is_multi_mode():
            return bool(getattr(active_model, "visible", False)) if active_model is not None else False
        return bool(magnifier_enabled(self._view))

    def prepare_for_add(self) -> None:
        set_magnifier_enabled_flag(self._view, True)

    def reveal_object(self, object_id: str | None):
        model = self.object_state.set_object_visibility(object_id, True)
        if model is not None:
            set_magnifier_enabled_flag(self._view, True)
        self.store.emit_viewport_change()
        return model

    def hide_active(self):
        active = self.object_state.get_active_or_first_magnifier()
        if active is None:
            return None
        self.object_state.set_object_visibility(active.id, False)
        self.object_state.set_active_object(active.id)
        set_magnifier_enabled_flag(self._view, True)
        self.store.emit_viewport_change()
        return active.id

    def set_single_enabled(self, enabled: bool):
        set_magnifier_enabled_flag(self._view, enabled)
        model = self.object_state.ensure_active_magnifier(create_if_missing=enabled)
        if model is not None:
            self.object_state.set_object_visibility(model.id, bool(enabled))
        self.store.emit_viewport_change()
        return model

    def toggle_from_button(self, checked: bool):
        if self.is_multi_mode():
            active = self.object_state.get_active_or_first_magnifier()
            if active is None:
                return None
            if checked:
                return self.reveal_object(active.id)
            self.hide_active()
            return active
        return self.set_single_enabled(checked)

    def normalize_after_remove(self):
        total = self.total_count()
        if total <= 0:
            set_magnifier_enabled_flag(self._view, False)
            self.object_state.set_active_object(None)
            self.store.emit_viewport_change()
            return None

        active = self.object_state.get_active_or_first_magnifier()
        if active is None:
            set_magnifier_enabled_flag(self._view, False)
            self.store.emit_viewport_change()
            return None

        if total == 1:
            if not bool(getattr(active, "visible", False)):
                self.object_state.set_object_visibility(active.id, True)
            self.object_state.set_active_object(active.id)
            set_magnifier_enabled_flag(self._view, True)
            self.store.emit_viewport_change()
            return active

        set_magnifier_enabled_flag(self._view, True)
        self.store.emit_viewport_change()
        return active
