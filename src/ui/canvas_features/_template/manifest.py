"""
Feature manifest — the auto-discovery entry point.

The registries look for ``WIDGET_FEATURE`` and ``FEATURE`` in this module.
Export whichever your feature needs:

- ``WIDGET_FEATURE`` — presentation-layer hooks (reducers, commands, toolbar,
  settings, render overrides).
- ``FEATURE`` — scene-graph hooks (build, apply, hit-test).

A render-only feature (like filename_overlay) only needs WIDGET_FEATURE.
A scene-participating feature (like magnifier) needs both.
"""

from __future__ import annotations

from .widget import build_widget_feature

WIDGET_FEATURE = build_widget_feature()
