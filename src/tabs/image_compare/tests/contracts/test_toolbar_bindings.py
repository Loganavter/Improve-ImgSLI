"""Toolbar binding dogma.

Every ``CanvasFeatureToolbarBinding`` has a unique ``control_id``, exposes
callable handlers, and forwards toolbar values to the feature's commands.

Dogma source: docs/dev/CONTRACTS.md §CanvasFeatureToolbarBinding.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.store import Store
from ui.canvas_infra.scene.registry import get_canvas_registry
import tabs.image_compare.canvas.features as image_compare_features

get_canvas_registry("image_compare").register_package(image_compare_features)


def get_canvas_feature_toolbar_bindings():
    return get_canvas_registry("image_compare").get_feature_toolbar_bindings()

def test_toolbar_bindings_have_unique_control_ids():
    """CONTRACTS.md: CanvasFeatureToolbarBinding control ids are stable and unique."""
    bindings = get_canvas_feature_toolbar_bindings()
    control_ids = [binding.control_id for binding in bindings]

    assert control_ids
    assert len(control_ids) == len(set(control_ids))

def test_toolbar_bindings_reference_callable_handlers():
    """CONTRACTS.md: toolbar bindings expose callable handlers for wired controls."""
    handler_fields = (
        "on_toggled",
        "on_value_changed",
        "on_right_clicked",
        "on_middle_clicked",
        "on_pressed",
        "on_released",
        "sync_state",
    )

    for binding in get_canvas_feature_toolbar_bindings():
        assert binding.control_id
        assert any(getattr(binding, field) is not None for field in handler_fields), (
            f"{binding.control_id} has no handlers"
        )
        for field in handler_fields:
            handler = getattr(binding, field)
            if handler is not None:
                assert callable(handler), f"{binding.control_id}.{field} is not callable"

def test_divider_width_toolbar_binding_executes_feature_commands(monkeypatch):
    """CONTRACTS.md: toolbar value handlers forward the value to feature commands."""
    calls = []

    def _record_command(store, feature_name, command_id, *args, **kwargs):
        calls.append((store, feature_name, command_id, args, kwargs))

    monkeypatch.setattr(
        "ui.canvas_infra.scene.feature_state_api.execute_feature_command",
        _record_command,
    )

    binding = next(
        binding
        for binding in get_canvas_feature_toolbar_bindings()
        if binding.control_id == "divider.width"
    )
    presenter = SimpleNamespace(store=Store())

    binding.on_value_changed(presenter, 7)

    assert [(feature, command, args) for _, feature, command, args, _ in calls] == [
        ("divider", "toggle_visibility", (True,)),
        ("divider", "set_thickness", (7,)),
    ]
