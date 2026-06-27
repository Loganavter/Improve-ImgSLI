"""Per-session state model for the image_compare tab.

Most of image_compare's interesting state already lives on the workspace
session's ``viewport`` and ``document`` — those are swapped automatically
when the active session changes. The dataclass below captures the
UI-only bits that are NOT in viewport: a couple of toolbar toggles and
the per-slot edit names.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ImageCompareState:
    show_file_names: bool = False
    edit_name_1: str = ""
    edit_name_2: str = ""
