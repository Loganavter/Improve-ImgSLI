from __future__ import annotations

from dataclasses import dataclass

def _get_session_handler(main_controller):
    if main_controller is None:
        return None
    if hasattr(main_controller, "increment_rating") or hasattr(
        main_controller, "set_rating"
    ):
        return main_controller
    return getattr(main_controller, "sessions", None)

@dataclass
class RatingGestureTransaction:
    main_controller: object
    image_number: int
    item_index: int
    starting_score: int
    _accumulated_delta: int = 0
    _is_finalized: bool = False

    def apply_delta(self, delta: int) -> None:
        if self._is_finalized:
            return
        self._accumulated_delta += delta
        session_handler = _get_session_handler(self.main_controller)
        if delta > 0:
            for _ in range(delta):
                if session_handler is not None and hasattr(
                    session_handler, "increment_rating"
                ):
                    session_handler.increment_rating(
                        self.image_number, self.item_index
                    )
        elif delta < 0:
            for _ in range(-delta):
                if session_handler is not None and hasattr(
                    session_handler, "decrement_rating"
                ):
                    session_handler.decrement_rating(
                        self.image_number, self.item_index
                    )

    def rollback(self) -> None:
        if self._is_finalized:
            return
        if self._accumulated_delta != 0:
            session_handler = _get_session_handler(self.main_controller)
            if session_handler is not None and hasattr(session_handler, "set_rating"):
                session_handler.set_rating(
                    self.image_number, self.item_index, self.starting_score
                )
        self._accumulated_delta = 0
        self._is_finalized = True

    def commit(self) -> None:
        if self._is_finalized:
            return

        self._is_finalized = True

    def has_changes(self) -> bool:
        return self._accumulated_delta != 0
