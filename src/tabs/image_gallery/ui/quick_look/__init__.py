"""Quick look ui package — thin owner re-export (file+package co-exist).

Python prefers the package directory over the sibling ``quick_look.py`` file,
so this ``__init__`` loads the file module via importlib and re-exports its
public symbols. This keeps ``from tabs.image_gallery.ui.quick_look import
QuickLookOverlay`` working while ``tabs.image_gallery.ui.quick_look.helpers``
remains a real subpackage. No QSS, painter pipeline only.
"""
from __future__ import annotations

import importlib.util
import pathlib as _ql_p
import sys as _ql_sys

try:
    _file_path = _ql_p.Path(__file__).parent.parent / "quick_look.py"
    if _file_path.is_file():
        _spec = importlib.util.spec_from_file_location("tabs.image_gallery.ui._quick_look_file", str(_file_path))
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            # Ensure __path__ trick inside the file still sees subpackage
            _sys_mod = _ql_sys.modules.get("tabs.image_gallery.ui.quick_look")
            # Temporarily place file module under alias to avoid recursion
            _ql_sys.modules["tabs.image_gallery.ui._quick_look_file"] = _mod
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            # Re-export public symbols for ``from tabs.image_gallery.ui.quick_look import X``
            for _name in (
                "QuickLookOverlay",
                "DIM_VEIL_ALPHA",
                "_SourceInsetHost",
                "_BarWidget",
                "_DualRestoredInventedBar",
                "_BandingCombHistogram",
                "_GenericHistogram",
                "_HistogramStub",
                "_load_preview_pixmap",
                "_thumb_pixmap",
                "_theme_color",
                "_token_color",
                "_set_colored_text",
                "_source_dimensions",
            ):
                if hasattr(_mod, _name):
                    globals()[_name] = getattr(_mod, _name)
            # Also keep file module accessible if someone imported it directly
            _ql_sys.modules["tabs.image_gallery.ui.quick_look"] = _ql_sys.modules[__name__]
            # Preserve subpackage path for helpers etc.
            try:
                _file_mod = _mod
                if hasattr(_file_mod, "__path__"):
                    # Merge file's __path__ (points to quick_look dir) already equals package __path__
                    pass
            except Exception:
                pass
except Exception:
    pass
