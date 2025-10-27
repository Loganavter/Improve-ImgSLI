"""
Dialog utilities and helpers for shared toolkit.

Provides common functionality for dialog windows:
- Base dialog class with standard setup
- Icon setup helpers
- Button scaffold creation
- Auto-sizing utilities
"""

from .dialog_helpers import (
    BaseDialog,
    setup_dialog_scaffold,
    setup_dialog_icon,
    auto_size_dialog
)

__all__ = [
    'BaseDialog',
    'setup_dialog_scaffold',
    'setup_dialog_icon',
    'auto_size_dialog'
]

