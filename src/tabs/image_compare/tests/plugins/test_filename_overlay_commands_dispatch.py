"""filename_overlay commands go through dispatch (P2 collapse), not direct write.

Regression: build_filename_overlay_commands must dispatch the matching
Set*Action via SettingsMutationService (no-op guard + persist + invalidate
+ emit preserved) instead of writing the viewport directly. Each command is
checked in two halves: (1) the dispatched action has the right type/field,
(2) the real tab reducer (ImageRenderConfigReducer) applies it to the
render config. A repeat call is a no-op returning False.
"""

from types import SimpleNamespace

from core.store_viewport import RenderConfig
from domain.types import Color
from plugins.settings.mutations import SettingsMutationService
from tabs.image_compare.canvas.features.filename_overlay.widget import (
    build_filename_overlay_commands,
)
from tabs.image_compare.state.reducers import ImageRenderConfigReducer


def _settings():
    render = RenderConfig()
    store = SimpleNamespace(viewport=SimpleNamespace(render_config=render))
    saved = []
    calls = {"invalidate": 0, "emit": 0, "core": 0}
    dispatched = []

    class _Dispatcher:
        def dispatch(self, action, scope=None):
            dispatched.append(action)
            store.viewport.render_config = ImageRenderConfigReducer.reduce(
                store.viewport.render_config, action
            )

    class _Manager:
        def _save_setting(self, key, value):
            saved.append((key, value))

    class _Notifier:
        def invalidate_render_cache(self):
            calls["invalidate"] += 1

        def emit_state_change(self, scope=None):
            calls["emit"] += 1

        def request_core_update(self):
            calls["core"] += 1

    store.get_dispatcher = lambda: _Dispatcher()
    store.get_active_workspace_session = lambda: None
    mutations = SettingsMutationService(store, _Manager(), _Notifier())
    settings = SimpleNamespace(mutations=mutations)
    return settings, store, dispatched, saved, calls


def _check(cmd_id, raw, field_name, expected, action_name, save_key=None):
    settings, store, dispatched, saved, calls = _settings()
    commands = build_filename_overlay_commands()
    assert commands[cmd_id](settings, raw) is True
    assert getattr(store.viewport.render_config, field_name) == expected, cmd_id
    kinds = [type(a).__name__ for a in dispatched]
    assert kinds[0] == action_name, (cmd_id, kinds)
    # invalidate parity: the old path called notifier.invalidate_render_cache
    # (which dispatches InvalidateRenderCacheAction via the store); the new
    # path dispatches it directly — same action reaches the reducer.
    assert "InvalidateRenderCacheAction" in kinds, (cmd_id, kinds)
    if save_key is not None:
        assert any(k == save_key for k, _v in saved), cmd_id
    assert calls == {"invalidate": 0, "emit": 1, "core": 1}, (cmd_id, calls)
    assert commands[cmd_id](settings, raw) is False, cmd_id
    assert len(dispatched) == len(kinds), cmd_id


def test_toggle_visibility_dispatches_and_noops():
    _check(
        "settings.toggle_visibility", True,
        "include_file_names_in_saved", True,
        "SetIncludeFileNamesInSavedAction", "include_file_names_in_saved",
    )


def test_scalar_commands_dispatch_with_normalization():
    cases = [
        ("settings.set_font_size", 130, "font_size_percent", 130, "SetFontSizePercentAction", "font_size_percent"),
        ("settings.set_font_size", -5, "font_size_percent", 1, "SetFontSizePercentAction", "font_size_percent"),
        ("settings.set_font_weight", 70, "font_weight", 70, "SetFontWeightAction", "font_weight"),
        ("settings.set_text_alpha", 60, "text_alpha_percent", 60, "SetTextAlphaPercentAction", "text_alpha_percent"),
        ("settings.set_draw_background", False, "draw_text_background", False, "SetDrawTextBackgroundAction", "draw_text_background"),
        ("settings.set_placement_mode", "center", "text_placement_mode", "center", "SetTextPlacementModeAction", "text_placement_mode"),
        ("settings.set_max_name_length", 30, "max_name_length", 30, "SetMaxNameLengthAction", "max_name_length"),
    ]
    for cmd_id, raw, field_name, expected, action_name, save_key in cases:
        _check(cmd_id, raw, field_name, expected, action_name, save_key)


def test_color_commands_dispatch_and_persist_hex():
    settings, store, dispatched, saved, _calls = _settings()
    commands = build_filename_overlay_commands()
    red = Color(255, 0, 0, 255)
    green = Color(0, 255, 0, 255)
    assert commands["settings.set_text_color"](settings, green) is True
    assert store.viewport.render_config.file_name_color == green
    assert ("filename_color", "#ff00ff00") in saved
    kinds = [type(a).__name__ for a in dispatched]
    assert kinds[0] == "SetFileNameColorAction", kinds
    assert "InvalidateRenderCacheAction" in kinds, kinds
    assert commands["settings.set_text_color"](settings, green) is False
    assert commands["settings.set_background_color"](settings, red) is True
    assert store.viewport.render_config.file_name_bg_color == red
    assert ("filename_bg_color", "#ffff0000") in saved
