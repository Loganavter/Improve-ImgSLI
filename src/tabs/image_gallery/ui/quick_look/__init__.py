"""Quick look package — the overlay class plus its helpers/bars/histograms.

The overlay lives in ``overlay.py`` and is imported NORMALLY (a static relative
import). It used to be a sibling ``ui/quick_look.py`` loaded through
``importlib.util.spec_from_file_location`` — a dynamic load a frozen build cannot
follow, wrapped in ``except Exception: pass``, so a packaged Windows build got an
EMPTY package and the gallery page could not be created (owner log 2026-10-28:
``cannot import name 'GALLERY_CARD_H'`` was the card package, the same proxy
shape; this one would have failed next). One module, one import mechanism.

Submodules (``helpers``, ``bars``, ``histograms``, ``artifacts``, ``insets``,
``labels_theme``, ``meta``, ``focus_restore``, ``headers``, ``nav_section``) stay
real submodules of this package.
"""

from __future__ import annotations

from . import overlay as _overlay
from .overlay import *  # noqa: F403 — the overlay's public surface
from .overlay import DIM_VEIL_ALPHA, QuickLookOverlay  # the names every caller uses


def __getattr__(name: str):
    """Answer any other name the old proxy used to copy (helpers, privates)."""
    return getattr(_overlay, name)


def __dir__() -> list[str]:
    return sorted(set(dir(_overlay)) | set(globals()))


__all__ = ["QuickLookOverlay", "DIM_VEIL_ALPHA"]
