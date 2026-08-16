"""Legacy import shim — shelf chrome moved to ``ui.widgets.shelf``.

The Session Picker shelf is now the shared ``ShelfWidget``
(``ui.widgets.shelf``); this module only re-exports ``OpaqueFillHost`` for
existing imports/tests that referenced the old location.
"""

from ui.widgets.shelf import OpaqueFillHost  # noqa: F401

__all__ = ["OpaqueFillHost"]
