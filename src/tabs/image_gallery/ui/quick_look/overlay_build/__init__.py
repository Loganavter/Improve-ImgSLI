"""Quick look overlay chrome + construction — package (was ``overlay_build.py``).

Module → package (plan-gallery-split-2026-10-17, Part C2). The former
``ui/quick_look/overlay_build.py`` was split by concern into:

- ``widgets``: painted chrome widgets (``_AccentPillHost`` / ``_CardPlate`` /
  ``_RuleWidget``) + the card-radius/nav-glyph chrome constants.
- ``icons``: the red-tinted ``delete`` icon resolver + lazy handle.
- ``build``: ``build_overlay_ui`` (the card layout assembly).

Bodies moved verbatim; class/function names and signatures are unchanged, and
every name is re-exported here so
``tabs.image_gallery.ui.quick_look.overlay_build`` (and the ``helpers`` shim)
keeps its full surface for importers and tests.

This is a NORMAL submodule of the ``quick_look`` package; the file/package
importlib shim lives in ``quick_look/__init__.py`` and is not involved here.
No QSS — painter pipeline only.
"""

from __future__ import annotations

from .build import QUICK_LOOK_NAV_GLYPH_PT, build_overlay_ui
from .icons import (
    _DANGER_TRASH_ICON_CACHE,
    _danger_trash_icon,
    _resolve_danger_trash_icon,
)
from .widgets import (
    QUICK_LOOK_CARD_RADIUS_PX,
    _AccentPillHost,
    _CardPlate,
    _RuleWidget,
)
