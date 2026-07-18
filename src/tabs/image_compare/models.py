"""Per-session state model for the image_compare tab.

Most of image_compare's interesting state already lives on the workspace
session's ``viewport`` and ``document`` — those are swapped automatically
when the active session becomes current. The dataclass below captures the
UI-only bits that are NOT in viewport: toolbar toggles, edit names, and a
camera snapshot so inactive sessions roundtrip zoom/pan through project I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImageCompareState:
    show_file_names: bool = False
    edit_name_1: str = ""
    edit_name_2: str = ""
    # Last-known canvas camera (synced on session leave / from host when active).
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
