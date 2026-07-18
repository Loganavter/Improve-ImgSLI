"""Feature-declared context-menu suppression zones.

Host canvas code must not hard-code magnifier (or other feature) geometry when
deciding whether a right-click may open a slot menu. Features declare zones via
``build_context_menu_zones``; the shared resolver walks them.
"""

from __future__ import annotations

from types import SimpleNamespace

from domain.types import Point
from tabs.image_compare.canvas.features.magnifier.input.context_menu_zones import (
    build_magnifier_context_menu_zones,
)
from tabs.image_compare.canvas.features.magnifier.scene.objects import (
    MagnifierCircle,
    MagnifierSceneObject,
)
from ui.canvas_infra.scene.context_menu_zones import (
    ContextMenuHitContext,
    is_context_menu_suppressed,
)
from ui.canvas_infra.scene.models import CanvasSceneGraph
from ui.canvas_infra.scene.widget_contract import CanvasFeatureContextMenuZone


def _combined_magnifier(*, center=(100.0, 100.0), radius=40.0) -> MagnifierSceneObject:
    cx, cy = center
    return MagnifierSceneObject(
        id="mag-combined",
        kind="magnifier",
        visible=True,
        is_combined=True,
        capture_center=Point(cx, cy),
        capture_radius=10.0,
        circles=(
            MagnifierCircle(center=Point(cx, cy), radius=radius, role="combined"),
        ),
        interactive_circle_index=0,
    )


def _split_magnifier(*, center=(100.0, 100.0), radius=40.0) -> MagnifierSceneObject:
    cx, cy = center
    return MagnifierSceneObject(
        id="mag-split",
        kind="magnifier",
        visible=True,
        is_combined=False,
        capture_center=Point(cx, cy),
        capture_radius=10.0,
        circles=(
            MagnifierCircle(center=Point(cx - 30.0, cy), radius=radius, role="left"),
            MagnifierCircle(center=Point(cx + 30.0, cy), radius=radius, role="right"),
        ),
        interactive_circle_index=0,
    )


def _canvas_with_scene(*objects) -> SimpleNamespace:
    scene = CanvasSceneGraph(objects=tuple(objects), active_object_id=objects[0].id)
    return SimpleNamespace(runtime_state=SimpleNamespace(_canvas_scene_graph=scene))


def _ctx(canvas, *, x: float, y: float) -> ContextMenuHitContext:
    return ContextMenuHitContext(
        store=SimpleNamespace(),
        canvas=canvas,
        local_pos=SimpleNamespace(x=lambda: x, y=lambda: y),
        session_type="image_compare",
    )


def _combined_zone() -> CanvasFeatureContextMenuZone:
    zones = build_magnifier_context_menu_zones()
    return next(z for z in zones if z.zone_id == "magnifier.combined_overlay")


def test_magnifier_declares_combined_overlay_zone():
    zones = build_magnifier_context_menu_zones()
    assert zones
    assert all(isinstance(z, CanvasFeatureContextMenuZone) for z in zones)
    assert any(z.zone_id == "magnifier.combined_overlay" for z in zones)


def test_combined_magnifier_suppresses_context_menu_on_overlay():
    canvas = _canvas_with_scene(_combined_magnifier())
    assert _combined_zone().suppresses(_ctx(canvas, x=100.0, y=100.0))


def test_combined_magnifier_allows_context_menu_outside_overlay():
    canvas = _canvas_with_scene(_combined_magnifier())
    assert not _combined_zone().suppresses(_ctx(canvas, x=300.0, y=300.0))


def test_split_magnifier_does_not_suppress_context_menu_on_overlay():
    canvas = _canvas_with_scene(_split_magnifier())
    assert not _combined_zone().suppresses(_ctx(canvas, x=70.0, y=100.0))


def test_resolver_returns_true_when_any_zone_matches(monkeypatch):
    from ui.canvas_infra.scene import context_menu_zones as zones_mod

    hit = CanvasFeatureContextMenuZone(
        zone_id="test.hit",
        suppresses=lambda ctx: True,
        priority=1,
    )
    miss = CanvasFeatureContextMenuZone(
        zone_id="test.miss",
        suppresses=lambda ctx: False,
        priority=2,
    )
    monkeypatch.setattr(
        zones_mod,
        "get_feature_context_menu_zones",
        lambda session_type: (miss, hit),
    )
    assert is_context_menu_suppressed(
        _ctx(_canvas_with_scene(_combined_magnifier()), x=0.0, y=0.0)
    )


def test_widget_feature_registers_context_menu_zones():
    import tabs.image_compare.canvas.features as image_compare_features
    from ui.canvas_infra.scene.registry import get_canvas_registry

    registry = get_canvas_registry("image_compare")
    registry.register_package(image_compare_features)
    zones = registry.get_feature_context_menu_zones()
    assert any(z.zone_id == "magnifier.combined_overlay" for z in zones)
