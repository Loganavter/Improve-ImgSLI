"""Feature store-commands emit ``emit_viewport_change`` exactly once; state
queries do not; a storeless command does not require the emit.

Dogma source: docs/dev/QRHI_CANVAS_FEATURES.md §Viewport Change Contract.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from core.store import Store
from ui.canvas_infra.scene.registry import get_canvas_registry
import tabs.image_compare.canvas.features as image_compare_features

get_canvas_registry("image_compare").register_package(image_compare_features)


def get_canvas_feature_state_commands():
    return get_canvas_registry("image_compare").get_feature_state_commands()


def get_canvas_feature_state_queries():
    return get_canvas_registry("image_compare").get_feature_state_queries()

def _required_params_after_first(handler):
    params = list(inspect.signature(handler).parameters.values())[1:]
    return [
        param
        for param in params
        if param.default is inspect.Signature.empty
        and param.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]

def _first_param_name(handler) -> str | None:
    params = list(inspect.signature(handler).parameters.values())
    return params[0].name if params else None

def test_no_arg_store_feature_commands_emit_viewport_change_once():
    """QRHI_CANVAS_FEATURES.md: feature state commands that mutate viewport must notify once."""
    commands = get_canvas_feature_state_commands()
    exercised = []

    for feature_name, feature_commands in commands.items():
        for command in feature_commands:
            if command.command_id.startswith("preview_"):
                continue
            if _first_param_name(command.handler) != "store":
                continue
            if _required_params_after_first(command.handler):
                continue

            store = Store()
            emissions = []
            store.on_change(emissions.append)

            result = command.handler(store)

            viewport_emissions = [
                scope for scope in emissions if str(scope).startswith("viewport")
            ]
            if result is False:
                assert viewport_emissions == [], (
                    f"{feature_name}.{command.command_id} emitted {viewport_emissions}"
                )
            elif isinstance(result, dict):
                assert viewport_emissions == [], (
                    f"{feature_name}.{command.command_id} emitted {viewport_emissions}"
                )
            else:
                assert len(viewport_emissions) == 1, (
                    f"{feature_name}.{command.command_id} emitted {viewport_emissions}"
                )
            exercised.append(f"{feature_name}.{command.command_id}")

    assert exercised

def test_feature_state_queries_do_not_emit_viewport_change():
    """QRHI_CANVAS_FEATURES.md: feature state queries must be read-only."""
    queries = get_canvas_feature_state_queries()
    exercised = []

    for feature_name, feature_queries in queries.items():
        for query in feature_queries:
            if _required_params_after_first(query.handler):
                continue

            store = Store()
            emissions = []
            store.on_change(emissions.append)
            arg = store.viewport.view_state if _first_param_name(query.handler) == "view_state" else store

            query.handler(arg)

            assert emissions == [], f"{feature_name}.{query.query_id} emitted {emissions}"
            exercised.append(f"{feature_name}.{query.query_id}")

    assert exercised

def test_storeless_feature_command_does_not_require_emit_viewport_change():
    """QRHI_CANVAS_FEATURES.md: commands tolerate bootstrap stores without emit_viewport_change."""
    command = next(
        command
        for command in get_canvas_feature_state_commands()["magnifier"]
        if command.command_id == "set_active_visibility_parts"
    )
    store = Store()
    store = SimpleNamespace(viewport=store.viewport, settings=store.settings)

    command.handler(store, left=False)
