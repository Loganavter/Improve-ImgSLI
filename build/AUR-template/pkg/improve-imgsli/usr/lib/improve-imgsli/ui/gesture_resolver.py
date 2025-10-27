from __future__ import annotations

from dataclasses import dataclass

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
		if delta > 0:
			for _ in range(delta):
				self.main_controller.increment_rating(self.image_number, self.item_index)
		elif delta < 0:
			for _ in range(-delta):
				self.main_controller.decrement_rating(self.image_number, self.item_index)

	def rollback(self) -> None:
		if self._is_finalized:
			return
		if self._accumulated_delta != 0:

			self.main_controller.set_rating(self.image_number, self.item_index, self.starting_score)
		self._accumulated_delta = 0
		self._is_finalized = True

	def commit(self) -> None:
		if self._is_finalized:
			return

		self._is_finalized = True

	def has_changes(self) -> bool:
		return self._accumulated_delta != 0
