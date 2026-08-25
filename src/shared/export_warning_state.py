"""Shared untested-export warning state helpers — single source for B5.

Both tabs duplicated ``_untested_export_suppressed`` / ``_suppress_untested``.
The dialog itself is already shared (``shared/untested_export_resolution.py``);
this module shares the suppress-flag plumbing.
"""

from __future__ import annotations


def is_untested_export_suppressed(settings) -> bool:
    """Return True when the user checked “Don’t show again”."""
    if settings is None:
        return False
    return bool(getattr(settings, "export_suppress_untested_resolution_warning", False))


def set_untested_export_suppressed(settings, manager, value: bool = True) -> None:
    """Persist the suppress flag to *settings* and via *manager* if present."""
    if settings is not None:
        try:
            settings.export_suppress_untested_resolution_warning = bool(value)
        except Exception:
            pass
    if manager is not None:
        try:
            manager._save_setting("export_suppress_untested_resolution_warning", bool(value))
        except Exception:
            pass
