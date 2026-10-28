"""Gallery card package — the card factory plus its region/row/badge helpers.

The implementation is ``factory.py`` and it is imported NORMALLY (a static
relative import). It used to be a sibling ``ui/card.py`` loaded through
``importlib.util.spec_from_file_location`` because a package shadows the file of
the same name; that dynamic load is invisible to a frozen build, so the packaged
Windows app answered::

    Failed to create page for tab 'image_gallery': cannot import name
    'GALLERY_CARD_H' from 'tabs.image_gallery.ui.card'

— the proxy's ``except Exception`` had turned a missing file into an EMPTY
namespace, and the gallery could not be opened at all (owner log 2026-10-28).
One module, one import mechanism: the sibling layout is what ``ui/list`` already
uses (``ui/list/card.py`` inside its package), and a static import is collected
by PyInstaller.

Submodules (``dots``, ``painters``, ``context_menu``, …) stay real submodules of
this package; nothing reads ``ui/card.py`` any more.
"""

from __future__ import annotations

from . import factory as _factory
from .factory import *  # noqa: F403 — the factory's public surface
from .factory import (  # explicit, so a reader sees the names most code uses
    GALLERY_CARD_H,
    GALLERY_CARD_W,
    build_gallery_card,
    update_gallery_card,
)


def __getattr__(name: str):
    """Answer any other name the old proxy used to copy (helpers, privates)."""
    return getattr(_factory, name)


def __dir__() -> list[str]:
    return sorted(set(dir(_factory)) | set(globals()))


__all__ = [
    "dots",
    "painters",
    "regions",
    "visuals",
    "hover",
    "context_menu",
    "build_gallery_card",
    "update_gallery_card",
    "GALLERY_CARD_W",
    "GALLERY_CARD_H",
]
