"""Per-session state model for the image_compare tab.

Most of image_compare's interesting state already lives on the workspace
session's ``viewport`` and ``document`` — those are swapped automatically
when the active session becomes current. The dataclass below captures the
UI-only bits that are NOT in viewport: a camera snapshot so inactive
sessions roundtrip zoom/pan through project I/O.

The "file names enabled" flag is NOT duplicated here — the Store's
``viewport.render_config.include_file_names_in_saved`` is the single
source of truth (toolbar, canvas filename_overlay, export, and the
caption-editor panel all read it). Caption texts likewise come from
``DocumentModel`` display names, which the editor syncs from via
``chrome_sync``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImageCompareState:
    # Last-known canvas camera (synced on session leave / from host when active).
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0