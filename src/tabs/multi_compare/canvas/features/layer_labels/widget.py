"""
Widget feature definition for layer_labels — presentation-layer contract.

Phase A scaffolding only: no-op reducers, no commands yet. Existing behavior
(LabelsOverlaySource in scene/passes/labels.py) is untouched; this package
exists only so the feature is discoverable by the canvas_infra registries
ahead of the Phase B pass-contract conversion.
"""

from __future__ import annotations

from ui.canvas_infra.scene.widget_contract import CanvasWidgetFeature


def _noop_reduce_view_state(view_state, action):
    return view_state


def _noop_reduce_render_config(config, action):
    return config


def _build_commands() -> dict[str, object]:
    return {}


COMMAND_ALIASES = ()


def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="layer_labels",
        reduce_view_state=_noop_reduce_view_state,
        reduce_render_config=_noop_reduce_render_config,
        build_commands=_build_commands,
        command_aliases=COMMAND_ALIASES,
    )
