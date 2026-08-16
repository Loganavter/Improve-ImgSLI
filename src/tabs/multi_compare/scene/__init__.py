"""Redux-style state management for the multi-compare tab.

``MultiCompareState`` is an immutable dataclass; ``MultiCompareAction`` +
``actions`` factories + the pure ``reduce`` live here, and
``MultiCompareStore`` is a facade over the core Dispatcher + the active
session's ``multi_compare.state`` slot (with a standalone mode for tests) —
see state-unification-plan.md (private improve-imgsli-internal-docs repo).(private improve-imgsli-internal-docs repo).
"""

from tabs.multi_compare.scene.store import (
    MultiCompareAction,
    MultiCompareStore,
    actions,
    reduce,
)

__all__ = [
    "MultiCompareAction",
    "MultiCompareStore",
    "actions",
    "reduce",
]
