"""Redux-style state management for the multi-compare tab.

This package exists as the migration target for the legacy mutable
``MultiCompareState`` flow in :mod:`tabs.multi_compare.models` and
:mod:`tabs.multi_compare.widget`. During the migration the new modules live
side-by-side with the old API: ``tree_ops`` mirrors the mutation-style helpers
in ``models`` with pure variants, and ``store`` provides an action / reducer /
dispatch loop scoped to the multi-compare tab. Once every call site is on the
new API, the legacy helpers and direct ``self.state.X = Y`` mutations get
deleted.
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
