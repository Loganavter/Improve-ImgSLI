"""Host action-catalog contract (Find Action / command palette).

UI-agnostic types only — the live registry lives in ``ui.actions``.
"""

from __future__ import annotations

from core.actions.types import ActionDescriptor, ActionTarget

__all__ = [
    "ActionDescriptor",
    "ActionTarget",
]
