"""Transaction — single-dispatch batch of actions (plan_image_pipeline.md Phase 5).

Replaces 6–10 dispatches per ``set_current_image`` with one dispatch that
reduces to one ``Store`` / one ``ViewportState`` (+ one ``DocumentModel``)
and one ``emit_state_change``. ``Dispatcher`` is already reentrant-safe
(``dispatcher.py:186`` snapshot + release before emit), so ``on_change ->
dispatch`` needs no ``QTimer``.

Usage:
    from core.state_management.transaction import TransactionAction
    store.transact([SetFullResImageAction(...), SetImagePathAction(...)], scope="document")

Or via ``Store.transact`` helper (``store.py``):
    store.transact([action1, action2], scope="document")
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.state_management.action_base import Action, ActionType


@dataclass
class TransactionAction(Action):
    actions: list[Action] = field(default_factory=list)

    def __init__(self, actions: list[Action] | None = None):
        super().__init__(type=ActionType.TRANSACTION)
        self.actions = list(actions) if actions is not None else []

    def get_payload(self):  # type: ignore[override]
        return {"actions": [getattr(a, "type", str(a)) for a in self.actions]}
