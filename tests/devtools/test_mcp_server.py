"""MCP app server — catalog lint + JSON-RPC round trips (no GUI, no display).

Falsification story: ``mcp-server/`` is new in this task, so a base checkout has
no ``app`` package to import and every assertion here fails at collection.

The suite deliberately never boots the app: it drives ``MCPProtocol`` with an
injected ``AppBackend`` snapshot/launcher/settings writer, and the one real
subprocess round trip only exercises methods that read the declared catalog or
the devtools surface list. ``list_actions`` is proven against a *real*
``ActionRegistry`` (platform actions registered in-process) so the ids asserted
are registry ids, not fixtures restating an implementation detail.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from app import catalog  # noqa: E402
from app.backend import AppBackend  # noqa: E402
from app.protocol import MCPProtocol  # noqa: E402

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_ANNOTATION_KEYS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


def _registry_snapshot() -> dict:
    """Snapshot built from a real ActionRegistry + real Store defaults."""
    from ui.actions.platform import register_platform_actions
    from ui.actions.registry import ActionRegistry

    from devtools.app_snapshot import dump_actions, dump_sessions

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
    from core.store import Store

    store = Store()
    return {
        "schema": "imgsli-app-snapshot/1",
        "actions": dump_actions(registry),
        "state": {"settings": {"theme": "dark", "current_language": "en"}},
        "sessions": dump_sessions(store),
        "theme": "dark",
        "language": "en",
        "ui_scale_factor": 1.0,
    }


@pytest.fixture
def wired(tmp_path):
    """(protocol, backend, calls) with every external effect faked."""
    snapshot = _registry_snapshot()
    calls: dict[str, list] = {"tabs": [], "launches": [], "settings": []}

    def runner(tab):
        calls["tabs"].append(tab)
        return snapshot

    def launcher(args):
        calls["launches"].append(args)
        return 4242

    def writer(key, value):
        calls["settings"].append((key, value))

    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=runner,
        launcher=launcher,
        settings_writer=writer,
    )
    return MCPProtocol(backend), backend, calls


def _request(protocol: MCPProtocol, method: str, params: dict | None = None, *, rid: int = 1):
    message = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
    response = protocol.handle(message)
    assert response is not None and response["id"] == rid
    return response


def _call(protocol: MCPProtocol, name: str, arguments: dict | None = None):
    response = _request(protocol, "tools/call", {"name": name, "arguments": arguments or {}})
    assert "error" not in response, response.get("error")
    return response["result"]


# --- catalog lint -----------------------------------------------------------


def test_tools_list_is_a_valid_deterministic_catalog(wired):
    protocol, _backend, _calls = wired
    tools = _request(protocol, "tools/list")["result"]["tools"]

    names = [tool["name"] for tool in tools]
    assert len(names) == len(set(names)), "tool names must be unique"
    assert names == [tool["name"] for tool in catalog.TOOLS], "order must be catalog order"
    assert len(tools) <= 15, "catalog must stay small"

    for tool in tools:
        assert _NAME_RE.match(tool["name"]), tool["name"]
        assert 200 <= len(tool["description"]) <= 400, (
            f"{tool['name']} description is {len(tool['description'])} chars"
        )
        annotations = tool["annotations"]
        for key in _ANNOTATION_KEYS:
            assert isinstance(annotations.get(key), bool), (tool["name"], key)
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        for prop, spec in schema["properties"].items():
            assert spec.get("description"), f"{tool['name']}.{prop} needs a description"
        out = tool["outputSchema"]
        assert out and out["type"] == "object" and out.get("properties")


def test_finite_values_expose_enums_and_defaults(wired):
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}

    assert tools["set_theme"]["inputSchema"]["properties"]["theme"]["enum"] == ["light", "dark"]
    assert tools["set_language"]["inputSchema"]["properties"]["language"]["enum"] == list(
        catalog.LANGUAGES
    )
    assert tools["open_tab"]["inputSchema"]["properties"]["tab"]["enum"] == list(catalog.TAB_KINDS)
    read_log = tools["read_log"]["inputSchema"]["properties"]["n"]
    assert read_log["default"] == 200 and read_log["type"] == "integer"
    assert tools["list_actions"]["inputSchema"]["additionalProperties"] is False


def test_read_and_write_tools_do_not_mix_annotations(wired):
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}

    for name in ("list_actions", "list_sessions", "get_state", "read_log", "query_trace",
                 "dump_ui_layout", "list_surfaces"):
        annotations = tools[name]["annotations"]
        assert annotations["readOnlyHint"] is True, name
        assert annotations["destructiveHint"] is False, name

    for name in ("open_tab", "run_action", "open_folder", "set_theme", "set_language",
                 "capture_surface"):
        assert tools[name]["annotations"]["readOnlyHint"] is False, name
    assert tools["run_action"]["annotations"]["destructiveHint"] is True
    for tool in tools.values():
        assert tool["annotations"]["openWorldHint"] is False, tool["name"]


# --- tools ------------------------------------------------------------------


def test_list_actions_returns_registry_ids(wired):
    protocol, _backend, _calls = wired
    result = _call(protocol, "list_actions")
    assert result["isError"] is False
    structured = result["structuredContent"]
    ids = {row["action_id"] for row in structured["actions"]}
    assert structured["count"] == len(ids)
    # Real ActionRegistry ids from ui.actions.platform.
    assert "platform.settings" in ids
    assert "platform.help" in ids
    assert all(isinstance(row["label"], str) and row["label"] for row in structured["actions"])


def test_list_actions_owner_tab_opens_that_tab(wired):
    protocol, _backend, calls = wired
    _call(protocol, "list_actions", {"owner_tab": "image_compare"})
    assert "image_compare" in calls["tabs"], "tab catalog needs the tab opened first"


def test_unknown_action_id_is_tool_error_with_fix_hint(wired):
    protocol, _backend, calls = wired
    result = _call(protocol, "run_action", {"action_id": "platform.does_not_exist"})
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "not a registered Find Action" in text
    assert "Hint:" in text and "list_actions" in text
    assert calls["launches"] == [], "an unknown id must not launch the app"


def test_run_action_known_id_launches_with_flag(wired):
    protocol, _backend, calls = wired
    result = _call(protocol, "run_action", {"action_id": "platform.settings"})
    assert result["structuredContent"]["launched"] is True
    assert result["structuredContent"]["pid"] == 4242
    assert calls["launches"] == [["--run-action", "platform.settings"]]


def test_set_theme_persists_and_invalidates_snapshot(wired):
    protocol, _backend, calls = wired
    _call(protocol, "list_actions")  # warm the cache
    result = _call(protocol, "set_theme", {"theme": "light"})
    assert result["structuredContent"]["persisted"] is True
    assert calls["settings"] == [("theme", "light")]
    assert result["structuredContent"]["applies_on"] == "next app start"
    _call(protocol, "list_actions")
    assert calls["tabs"].count(None) == 2, "snapshot must be re-read after a mutation"


def test_open_folder_rejects_missing_directory(wired, tmp_path):
    protocol, _backend, calls = wired
    result = _call(protocol, "open_folder", {"path": str(tmp_path / "nope")})
    assert result["isError"] is True
    assert "not an existing directory" in result["content"][0]["text"]
    assert calls["launches"] == []


def test_open_folder_existing_dir_launches_gallery(wired, tmp_path):
    protocol, _backend, calls = wired
    result = _call(protocol, "open_folder", {"path": str(tmp_path)})
    assert result["structuredContent"]["routed"] is False
    assert calls["launches"] == [["--open-tab", "image_gallery"]]


def test_list_surfaces_does_not_need_a_display(wired, monkeypatch):
    protocol, _backend, _calls = wired
    monkeypatch.delenv("DISPLAY", raising=False)
    result = _call(protocol, "list_surfaces")
    names = {row["name"] for row in result["structuredContent"]["surfaces"]}
    assert {"settings", "gallery-populated"} <= names


def test_get_state_slice_and_bad_path(wired):
    protocol, _backend, _calls = wired
    good = _call(protocol, "get_state", {"path": "settings.theme"})
    assert good["structuredContent"]["state"] == "dark"
    bad = _call(protocol, "get_state", {"path": "settings.nope"})
    assert bad["isError"] is True
    assert "no state at path" in bad["content"][0]["text"]


# --- protocol errors --------------------------------------------------------


def test_invalid_arguments_are_protocol_errors_not_tool_results(wired):
    protocol, _backend, _calls = wired
    unknown = _request(protocol, "tools/call", {"name": "read_log", "arguments": {"bogus": 1}})
    assert unknown["error"]["code"] == -32602
    bad_enum = _request(protocol, "tools/call", {"name": "set_theme", "arguments": {"theme": "blue"}})
    assert bad_enum["error"]["code"] == -32602
    missing = _request(protocol, "tools/call", {"name": "run_action", "arguments": {}})
    assert missing["error"]["code"] == -32602


def test_modern_envelope_is_validated(wired):
    protocol, _backend, _calls = wired
    missing_caps = _request(
        protocol,
        "tools/list",
        {"_meta": {"protocolVersion": "2026-07-28"}},
    )
    assert missing_caps["error"]["code"] == -32602
    unsupported = _request(
        protocol,
        "tools/list",
        {"_meta": {"protocolVersion": "1999-01-01", "clientCapabilities": {}}},
    )
    assert unsupported["error"]["code"] == -32022
    assert unsupported["error"]["data"]["supported"] == ["2026-07-28"]


def test_server_discover_advertises_modern_version(wired):
    protocol, _backend, _calls = wired
    result = _request(
        protocol,
        "server/discover",
        {"_meta": {"protocolVersion": "2026-07-28", "clientCapabilities": {}}},
    )["result"]
    assert result["supportedVersions"] == ["2026-07-28"]
    assert result["resultType"] == "complete"
    assert {"tools", "resources", "prompts"} <= set(result["capabilities"])


def test_unknown_method_is_method_not_found(wired):
    protocol, _backend, _calls = wired
    assert _request(protocol, "does/not/exist")["error"]["code"] == -32601


def test_notifications_get_no_response(wired):
    protocol, _backend, _calls = wired
    assert protocol.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


# --- resources + prompts ----------------------------------------------------


def test_resources_list_and_read_app_actions(wired):
    protocol, _backend, _calls = wired
    listing = _request(protocol, "resources/list")["result"]
    uris = [item["uri"] for item in listing["resources"]]
    assert uris == sorted(uris), "resources must be deterministic"
    assert "app://actions" in uris

    read = _request(protocol, "resources/read", {"uri": "app://actions"})["result"]
    payload = json.loads(read["contents"][0]["text"])
    assert any(row["action_id"] == "platform.settings" for row in payload["actions"])


def test_resource_templates_listed(wired):
    protocol, _backend, _calls = wired
    templates = _request(protocol, "resources/templates/list")["result"]["resourceTemplates"]
    uris = [item["uriTemplate"] for item in templates]
    assert uris == sorted(uris)
    assert "app://action/{id}" in uris
    assert "app://tab/{name}/layout" in uris


def test_theme_resource_reports_snapshot(wired):
    protocol, _backend, _calls = wired
    read = _request(protocol, "resources/read", {"uri": "app://theme"})["result"]
    payload = json.loads(read["contents"][0]["text"])
    assert payload["theme"] == "dark"
    assert payload["language"] == "en"


def test_prompts_list_and_get(wired):
    protocol, _backend, _calls = wired
    prompts = _request(protocol, "prompts/list")["result"]["prompts"]
    assert [prompt["name"] for prompt in prompts] == ["diagnose_gallery", "capture_and_inspect"]

    got = _request(protocol, "prompts/get", {"name": "diagnose_gallery", "arguments": {"symptom": "blank"}})["result"]
    assert got["messages"][0]["role"] == "user"
    assert "blank" in got["messages"][0]["content"]["text"]


def test_unknown_prompt_is_reported(wired):
    protocol, _backend, _calls = wired
    response = _request(protocol, "prompts/get", {"name": "nope"})
    assert response["error"]["code"] == -32602
    assert "unknown prompt" in response["error"]["message"]


# --- stdio round trip -------------------------------------------------------

_STDIO_MESSAGES = [
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
     "params": {"name": "list_surfaces", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
     "params": {"name": "no_such_tool", "arguments": {}}},
    {"jsonrpc": "2.0", "id": 5, "method": "server/discover",
     "params": {"_meta": {"protocolVersion": "2026-07-28", "clientCapabilities": {}}}},
]


def test_structured_content_matches_declared_output_schema(wired, tmp_path):
    """Every successful result must validate against its own outputSchema."""
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}
    calls = {
        "list_actions": {},
        "list_sessions": {},
        "get_state": {"path": "settings.theme"},
        "list_surfaces": {},
        "set_theme": {"theme": "dark"},
        "set_language": {"language": "en"},
        "open_tab": {"tab": "image_compare"},
        "open_folder": {"path": str(tmp_path)},
        "run_action": {"action_id": "platform.settings"},
    }
    for name, arguments in calls.items():
        result = _call(protocol, name, arguments)
        structured = result["structuredContent"]
        schema = tools[name]["outputSchema"]
        assert set(schema.get("required") or ()) <= set(structured), name
        assert set(structured) <= set(schema["properties"]), (name, set(structured))
        assert isinstance(json.loads(result["content"][0]["text"]), (dict, list)), name


def test_error_results_omit_structured_content(wired):
    protocol, _backend, _calls = wired
    result = _call(protocol, "run_action", {"action_id": "nope"})
    assert result["isError"] is True
    assert "structuredContent" not in result


def test_stdio_round_trip_over_pipes(tmp_path):
    payload = "\n".join(json.dumps(message) for message in _STDIO_MESSAGES) + "\n"
    env = dict(
        __import__("os").environ,
        PYTHONDONTWRITEBYTECODE="1",
        IMGSLI_MCP_ARTIFACTS=str(tmp_path / "artifacts"),
    )
    proc = subprocess.run(
        [sys.executable, str(MCP_DIR / "app" / "server.py"), "--repo-root", str(REPO_ROOT)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    # 5 responses: the initialized notification yields none.
    assert [entry["id"] for entry in lines] == [1, 2, 3, 4, 5]
    by_id = {entry["id"]: entry for entry in lines}
    assert by_id[1]["result"]["protocolVersion"] == "2025-11-25"
    assert len(by_id[2]["result"]["tools"]) == len(catalog.TOOLS)
    assert by_id[3]["result"]["isError"] is False
    assert by_id[4]["error"]["code"] == -32602, "unknown tool name is invalid params"
    assert by_id[5]["result"]["supportedVersions"] == ["2026-07-28"]
    assert "serving stdio" in proc.stderr


def test_check_flag_prints_catalog_without_serving():
    proc = subprocess.run(
        [sys.executable, str(MCP_DIR / "app" / "server.py"), "--check"],
        capture_output=True,
        text=True,
        env=dict(__import__("os").environ, PYTHONDONTWRITEBYTECODE="1"),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["protocolVersion"] == "2026-07-28"
    assert summary["toolCount"] == len(catalog.TOOLS)
