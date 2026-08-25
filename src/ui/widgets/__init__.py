"""ui.widgets package — submodules only.

Former re-export facade (Label, CheckBox, etc. via __getattr__) removed
2026-08-25 (cross-module review C8 — zero importers, kept only for package
marker). Import directly from ``sli_ui_toolkit.widgets`` or the concrete
submodule (e.g. ``ui.widgets.slider_hint``).
"""
