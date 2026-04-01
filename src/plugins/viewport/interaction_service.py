from __future__ import annotations

from domain.types import Point

class ViewportInteractionService:
    def __init__(self, runtime, store):
        self.runtime = runtime
        self.store = store
        self._interaction_session_counter = int(
            getattr(self.store.viewport.interaction_state, "interaction_session_id", 0)
        )

    def begin_user_interaction(self) -> None:
        viewport = self.store.viewport
        if getattr(viewport.interaction_state, "is_user_interacting", False):
            return
        self._interaction_session_counter = max(
            self._interaction_session_counter + 1,
            int(getattr(viewport.interaction_state, "interaction_session_id", 0)) + 1,
        )
        viewport.interaction_state.interaction_session_id = self._interaction_session_counter
        viewport.interaction_state.is_user_interacting = True
        self.runtime.emit_update()
        self.runtime.capture_recording_checkpoint(force_advance_frame=True)

    def end_user_interaction(self) -> None:
        viewport = self.store.viewport
        if not getattr(viewport.interaction_state, "is_user_interacting", False):
            return
        viewport.interaction_state.is_user_interacting = False
        self.runtime.emit_update()
        self.runtime.capture_recording_checkpoint(force_advance_frame=True)

    def clamp_capture_position(self):
        capture_pos = self.store.viewport.view_state.capture_position_relative
        if not self.store.viewport.session_data.image_state.image1:
            return

        unified_w, unified_h = self.store.viewport.session_data.image_state.image1.size
        if unified_w <= 0 or unified_h <= 0:
            return

        ref_dim = min(unified_w, unified_h)
        capture_size_px = self.store.viewport.view_state.capture_size_relative * ref_dim
        radius_rel_x = (capture_size_px / 2.0) / unified_w if unified_w > 0 else 0
        radius_rel_y = (capture_size_px / 2.0) / unified_h if unified_h > 0 else 0

        self.store.viewport.view_state.capture_position_relative = Point(
            max(radius_rel_x, min(capture_pos.x, 1.0 - radius_rel_x)),
            max(radius_rel_y, min(capture_pos.y, 1.0 - radius_rel_y)),
        )

    def compute_unfreeze_offset(self):
        frozen = self.store.viewport.view_state.frozen_capture_point_relative
        if not frozen:
            return None

        drawing_width = self.store.viewport.geometry_state.pixmap_width
        drawing_height = self.store.viewport.geometry_state.pixmap_height
        if drawing_width <= 0 or drawing_height <= 0:
            return None

        target_max_dim = float(max(drawing_width, drawing_height))
        offset = self.store.viewport.view_state.magnifier_offset_relative
        capture = self.store.viewport.view_state.capture_position_relative

        frozen_px_x = frozen.x * drawing_width
        frozen_px_y = frozen.y * drawing_height
        offset_px_x = offset.x * target_max_dim
        offset_px_y = offset.y * target_max_dim
        target_px_x = frozen_px_x + offset_px_x
        target_px_y = frozen_px_y + offset_px_y

        capture_px_x = capture.x * drawing_width
        capture_px_y = capture.y * drawing_height
        new_offset_x = (
            (target_px_x - capture_px_x) / target_max_dim if target_max_dim > 0 else 0
        )
        new_offset_y = (
            (target_px_y - capture_px_y) / target_max_dim if target_max_dim > 0 else 0
        )
        return Point(new_offset_x, new_offset_y)
