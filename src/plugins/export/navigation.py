"""Keyboard navigation for the Export dialog.

The dialog had **no** navigation section: arrow keys on its form controls went
nowhere and the shared ``NavigationManager`` had no owner for the window.  It
is a vertical form of rows (output path, format, resolution, quality, PNG
options, background, metadata, comment, action bar), some of which toggle
visibility with the chosen format — so it registers the toolkit's zero-config
``AutoNavigationSection`` over itself, whose rows are recomputed from the
currently visible ``StrongFocus`` widgets (hidden rows drop out instead of
stalling the walk).  Same shape as the Find Action palette dialog.

Registered once on construction; the manager's own ``destroyed`` hook drops
the section when the dialog is torn down.
"""

from __future__ import annotations

from sli_ui_toolkit.managers import AutoNavigationSection, NavigationManager


def register_export_navigation(dialog) -> None:
    """Register the dialog's auto row section (idempotent)."""
    if getattr(dialog, "_export_nav_section", None) is not None:
        return
    section = AutoNavigationSection(dialog, tag="export")
    dialog._export_nav_section = section
    NavigationManager.get_instance().register(dialog, section)


def unregister_export_navigation(dialog) -> None:
    """Drop the dialog's section (idempotent)."""
    if getattr(dialog, "_export_nav_section", None) is None:
        return
    NavigationManager.get_instance().unregister(dialog)
    dialog._export_nav_section = None
