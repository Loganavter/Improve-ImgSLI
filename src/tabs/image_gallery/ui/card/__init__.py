"""Gallery card package — thin owner proxy.

``tabs.image_gallery.ui.card`` is loaded as a package from this directory;
the thin owner implementation lives in the sibling file ``card.py`` (≈380 lines).
This ``__init__`` loads that file as ``_file`` and re-exports its public
surface so both ``import tabs.image_gallery.ui.card`` paths work and
``ui/card/*`` submodules are found via the package's ``__path__``.
Painter pipeline only (no setStyleSheet), lazy imports per CODE_PATTERNS.md.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path as _Path

# Load sibling file ``ui/card.py`` as a submodule to keep implementation
# single-sourced. Copy its attributes into this package namespace.
_pkg_dir = _Path(__file__).parent
_file_path = _pkg_dir.parent / "card.py"
_spec = importlib.util.spec_from_file_location("tabs.image_gallery.ui.card._file", _file_path)
if _spec and _spec.loader:
    _mod = importlib.util.module_from_spec(_spec)
    # Register temporarily to allow relative imports inside the file to resolve.
    sys.modules[_spec.name] = _mod
    try:
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    except Exception:
        # If file fails to load (e.g. during static analysis), keep package empty.
        _mod = None
    if _mod is not None:
        # Copy public attributes (including __getattr__ for lazy re-exports).
        for _k, _v in list(_mod.__dict__.items()):
            if _k.startswith("__") and _k not in ("__path__", "__getattr__", "__dir__"):
                continue
            globals()[_k] = _v
        # Keep package's __path__ (directory) — submodules live here.
        # File's __path__ is similar, but package's is authoritative.
        __path__ = list(getattr(_mod, "__path__", [])) or [str(_pkg_dir)]  # type: ignore[attr-defined]
        # Preserve __getattr__/__dir__ for lazy re-exports.
        if hasattr(_mod, "__getattr__"):
            __getattr__ = _mod.__getattr__  # type: ignore[attr-defined]
        if hasattr(_mod, "__dir__"):
            __dir__ = _mod.__dir__  # type: ignore[attr-defined]
        # Cleanup temp module name.
        sys.modules.pop(_spec.name, None)

__all__ = [
    "dots",
    "painters",
    "regions",
    "visuals",
    "hover",
    "context_menu",
    "build_gallery_card",
    "update_gallery_card",
]
