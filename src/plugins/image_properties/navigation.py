"""Keyboard navigation for the Image-properties dialog.

The dialog had **no** navigation section: arrow keys did nothing and the
``NavigationManager`` had no owner for the window.  It is a read-only document
canvas plus one action row (Copy all / Close), so registering the toolkit's
zero-config ``AutoNavigationSection`` over the whole dialog owns every
``StrongFocus`` control — the action row, the document surface and the CSD
title bar's Help-menu trigger.  Same shape as the Help dialog, which treats
its document view as an owned content target.

Registered once on construction; the manager's own ``destroyed`` hook drops
the section when the dialog is torn down.
"""

from __future__ import annotations

from sli_ui_toolkit.managers import AutoNavigationSection, NavigationManager


def register_image_properties_navigation(dialog) -> None:
    """Register the dialog's auto row section (idempotent)."""
    if getattr(dialog, "_image_properties_nav_section", None) is not None:
        return
    section = AutoNavigationSection(dialog, tag="image-properties")
    dialog._image_properties_nav_section = section
    NavigationManager.get_instance().register(dialog, section)
