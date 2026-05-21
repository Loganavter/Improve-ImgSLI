from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

def _make_store():
    return SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(),
            render_config=SimpleNamespace(),
            interaction_state=SimpleNamespace(is_dragging_overlay_handle=True),
        )
    )

def _make_canvas(store):
    return SimpleNamespace(
        runtime_state=SimpleNamespace(
            _store=store,
            _render_scene=SimpleNamespace(feature_overrides={}),
        ),
        set_overlay_coords=lambda *args, **kwargs: None,
    )

def _make_scene():
    from domain.types import Point
    from ui.canvas_features.magnifier.scene_objects import (
        MagnifierCircle,
        MagnifierSceneObject,
    )

    hidden_obj = MagnifierSceneObject(
        id="hidden",
        kind="magnifier",
        visible=False,
        capture_center=Point(10.0, 20.0),
        capture_radius=15.0,
        circles=(MagnifierCircle(center=Point(30.0, 40.0), radius=25.0, role="left"),),
    )
    active_obj = MagnifierSceneObject(
        id="active",
        kind="magnifier",
        visible=True,
        capture_center=Point(50.0, 60.0),
        capture_radius=20.0,
        circles=(MagnifierCircle(center=Point(70.0, 80.0), radius=35.0, role="left"),),
        interactive_circle_index=0,
        capture_color=None,
    )
    objects = (active_obj, hidden_obj)
    return SimpleNamespace(
        active_object_id="active",
        iter_objects=lambda kind=None: tuple(obj for obj in objects if kind is None or obj.kind == kind),
        get_object=lambda object_id: next((obj for obj in objects if obj.id == object_id), None),
    )

def test_apply_magnifier_objects_omits_interactive_payloads_in_export(monkeypatch):
    from ui.canvas_features.magnifier.feature import apply_magnifier_objects
    from ui.canvas_infra.scene.context import CanvasSceneApplyContext
    from ui.canvas_infra.scene.gl_pass_contract import SceneVisibility

    store = _make_store()
    canvas = _make_canvas(store)
    scene = _make_scene()

    monkeypatch.setattr(
        "ui.canvas_features.magnifier.feature.get_magnifier_widget_state",
        lambda view_state: SimpleNamespace(intersection_highlight_enabled=True),
    )
    monkeypatch.setattr(
        "ui.canvas_features.magnifier.feature.get_canvas_feature_command_by_alias",
        lambda alias: (lambda view_state: SimpleNamespace(color=SimpleNamespace(r=255, g=255, b=255, a=255)))
        if alias == "capture.widget_state"
        else None,
    )

    apply_magnifier_objects(
        scene,
        CanvasSceneApplyContext(
            canvas=canvas,
            geometry_state=SimpleNamespace(),
            use_quick_overlay=False,
            scene_visibility=SceneVisibility.EXPORT,
        ),
    )

    overrides = canvas.runtime_state._render_scene.feature_overrides
    assert overrides["capture_circles"]
    assert overrides["hidden_capture_circles"] == []
    assert overrides["hidden_magnifier_circles"] == []
    assert overrides["occluded_capture_arcs"] == []

def test_apply_magnifier_objects_keeps_interactive_payloads_in_interactive(monkeypatch):
    from ui.canvas_features.magnifier.feature import apply_magnifier_objects
    from ui.canvas_infra.scene.context import CanvasSceneApplyContext
    from ui.canvas_infra.scene.gl_pass_contract import SceneVisibility

    store = _make_store()
    canvas = _make_canvas(store)
    scene = _make_scene()

    monkeypatch.setattr(
        "ui.canvas_features.magnifier.feature.get_magnifier_widget_state",
        lambda view_state: SimpleNamespace(intersection_highlight_enabled=True),
    )
    monkeypatch.setattr(
        "ui.canvas_features.magnifier.feature.get_canvas_feature_command_by_alias",
        lambda alias: (lambda view_state: SimpleNamespace(color=SimpleNamespace(r=255, g=255, b=255, a=255)))
        if alias == "capture.widget_state"
        else None,
    )
    monkeypatch.setattr(
        "ui.canvas_features.magnifier.feature._compute_occluded_capture_arcs",
        lambda all_magnifiers, visible_magnifiers, active_object_id: [("arc", 1)],
    )

    apply_magnifier_objects(
        scene,
        CanvasSceneApplyContext(
            canvas=canvas,
            geometry_state=SimpleNamespace(),
            use_quick_overlay=False,
            scene_visibility=SceneVisibility.INTERACTIVE,
        ),
    )

    overrides = canvas.runtime_state._render_scene.feature_overrides
    assert overrides["hidden_capture_circles"]
    assert overrides["hidden_magnifier_circles"]
    assert overrides["occluded_capture_arcs"] == [("arc", 1)]

def test_magnifier_mode_service_no_longer_exposes_hidden_selection_gate():
    from ui.canvas_features.magnifier.mode import MagnifierModeService

    assert not hasattr(MagnifierModeService, "should_show_hidden_selection")
