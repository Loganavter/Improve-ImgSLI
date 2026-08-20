"""Register image_compare toolbar actions into the host action catalog.

Public API::

    from tabs.image_compare.actions import register_image_compare_actions, contribute_keymap_defaults

Internal layout:

- ``_common``: shared constants (``OWNER``, ``_BC_*``), ``_WidgetAction`` dataclass,
  spec tuples (``_SPECS``, ``_DIFF_OPTION_SPECS``, …), button dispatchers.
- ``_contribute``: all ``_contribute_*`` functions, the main
  ``register_image_compare_actions`` entry point, and ``contribute_keymap_defaults``.
"""

from tabs.image_compare.actions._contribute import (
    contribute_keymap_defaults,
    register_image_compare_actions,
)

__all__ = ["register_image_compare_actions", "contribute_keymap_defaults"]
