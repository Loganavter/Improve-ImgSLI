"""Runtime overlay snapshots are the authoritative live geometry source.

Dogma source: docs/dev/CANVAS_FEATURES.md §Canvas presentation.
"""

from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace


def test_feature_overlay_context_exposes_capture_circles():
    from tabs.image_compare.canvas.render_context import GLFeatureOverlayContext

    assert "capture_circles" in {
        field.name for field in fields(GLFeatureOverlayContext)
    }


def test_capture_ring_prefers_runtime_overlay_snapshot_over_scene_payload():
    from tabs.image_compare.canvas.features.capture.passes import CaptureRingPass

    ctx = SimpleNamespace(
        feature_overlay=SimpleNamespace(capture_circles=("runtime-capture",)),
        scene_frame=SimpleNamespace(
            feature_payloads={"capture_circles": ("scene-capture",)}
        ),
    )
    widget = SimpleNamespace(
        runtime_state=SimpleNamespace(_capture_circles=("state-capture",))
    )

    assert CaptureRingPass._resolve_capture_circles(widget, ctx) == ("runtime-capture",)


def test_magnifier_annotation_passes_prefer_runtime_overlay_snapshot():
    from tabs.image_compare.canvas.features.magnifier.passes import (
        HiddenSelectionPass,
        OccludedArcPass,
    )

    ctx = SimpleNamespace(
        feature_overlay=SimpleNamespace(
            hidden_capture_circles=("runtime-hidden-capture",),
            hidden_overlay_circles=("runtime-hidden-overlay",),
            occluded_capture_arcs=("runtime-arc",),
        ),
        scene_frame=SimpleNamespace(
            feature_payloads={
                "hidden_capture_circles": ("scene-hidden-capture",),
                "hidden_magnifier_circles": ("scene-hidden-overlay",),
                "occluded_capture_arcs": ("scene-arc",),
            }
        ),
    )

    assert HiddenSelectionPass._resolve_hidden_capture_circles(ctx) == (
        "runtime-hidden-capture",
    )
    assert HiddenSelectionPass._resolve_hidden_overlay_circles(ctx) == (
        "runtime-hidden-overlay",
    )
    assert OccludedArcPass._resolve_occluded_capture_arcs(ctx) == ("runtime-arc",)
