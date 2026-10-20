"""``devtools.app_snapshot`` — headless serialization of live app objects.

Pure functions over a real ``ActionRegistry`` / ``Store`` (no window, no Qt
loop), which is what the MCP server's ``list_actions``/``get_state``/
``list_sessions`` read. Falsification: the module is new — a base checkout has
no ``src/devtools/app_snapshot.py`` and these imports fail.
"""

from __future__ import annotations

from devtools.app_snapshot import (
    SNAPSHOT_SCHEMA,
    dump_actions,
    dump_sessions,
    dump_snapshot,
    dump_state,
    encode,
    resolve_path,
)


def _registry():
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry

    def _noop() -> None:
        return None

    registry = ActionRegistry()
    register_platform_actions(
        show_settings=_noop,
        show_help=_noop,
        new_session=_noop,
        show_find_action=_noop,
        quit_app=_noop,
        registry=registry,
    )
    return registry


def test_dump_actions_carries_registry_ids_and_metadata():
    rows = dump_actions(_registry())
    ids = [row["action_id"] for row in rows]
    assert "platform.settings" in ids
    assert ids == sorted(ids), "host actions sort by id"
    row = next(item for item in rows if item["action_id"] == "platform.settings")
    assert row["label"] and row["label_key"]
    assert "owner_tab" in row and "runnable" in row


def test_dump_sessions_from_real_store():
    from core.store import Store

    store = Store()
    sessions = dump_sessions(store)
    assert sessions, "a fresh Store has the session_picker session"
    assert sessions[0]["session_type"] == "session_picker"
    assert sum(1 for session in sessions if session["active"]) == 1


def test_dump_state_omits_runtime_cache_and_keeps_settings():
    from core.store import Store

    state = dump_state(Store())
    assert set(state) == {"settings", "workspace", "document", "tabs"}
    assert state["settings"]["theme"] == "auto"
    assert "sessions" in state["workspace"]
    assert "runtime_cache" not in state
    # Assertion surface: no live page/store session -> every tab is inactive.
    assert set(state["tabs"]) == {"image_gallery", "image_compare", "multi_compare"}
    assert all(row["active"] is False for row in state["tabs"].values())


def test_dump_snapshot_shape():
    from core.store import Store

    snapshot = dump_snapshot(Store(), _registry())
    assert snapshot["schema"] == SNAPSHOT_SCHEMA
    assert snapshot["sessions"] == snapshot["state"]["workspace"]["sessions"]
    assert snapshot["theme"] == "auto"
    assert isinstance(snapshot["actions"], list)


def test_resolve_path_walks_dicts_and_lists():
    data = {"settings": {"theme": "dark"}, "items": [{"id": 1}, {"id": 2}]}
    assert resolve_path(data, "settings.theme") == "dark"
    assert resolve_path(data, "items.1.id") == 2
    assert resolve_path(data, "items.9") is None
    assert resolve_path(data, "nope") is None
    assert resolve_path(data, None) is data


def test_encode_is_depth_capped_and_json_safe():
    from dataclasses import dataclass

    @dataclass
    class Inner:
        value: float = 1.5

    @dataclass
    class Outer:
        inner: Inner = None  # type: ignore[assignment]

    encoded = encode(Outer(inner=Inner()))
    assert encoded == {"inner": {"value": 1.5}}
    assert encode({"blob": object()})["blob"].startswith("<object object")
    deep = current = {}
    for _ in range(10):
        current["next"] = {}
        current = current["next"]
    assert "<max-depth>" in str(encode(deep))
