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

import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from app import catalog  # noqa: E402
from app.backend import AppBackend  # noqa: E402
from app.live import LiveBackend  # noqa: E402
from app.process_policy import (  # noqa: E402
    PRESERVED_LOG_NAME,
    ProcessRegistry,
    launch_env,
    pid_alive,
    preserve_live_log,
)
from app.protocol import (  # noqa: E402
    INVALID_REQUEST,
    MAX_REQUEST_LINE_BYTES,
    MCPProtocol,
    serve_stdio,
)
from core.evidence.journal import record_evidence, reset_journal, verdict  # noqa: E402

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
def wired(tmp_path, monkeypatch):
    """(protocol, backend, calls) with every external effect faked.

    Discovery is pinned at an empty tmp control dir so the suite can never
    attach to a real app instance that happens to be running on this machine.
    """
    monkeypatch.delenv("IMGSLI_MCP_CONTROL_SOCKET", raising=False)
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "no-instance"))
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
    assert len(tools) <= 28, "catalog must stay small (review prompt, not a magic number)"

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
    open_folder = tools["open_folder"]["inputSchema"]
    assert open_folder["properties"]["slot"]["enum"] == [1, 2]
    assert open_folder["properties"]["side"]["enum"] == ["left", "right", "top", "bottom"]
    assert open_folder["required"] == ["path"], "slot/side are optional placement hints"
    read_log = tools["read_log"]["inputSchema"]["properties"]["n"]
    assert read_log["default"] == 200 and read_log["type"] == "integer"
    assert tools["list_actions"]["inputSchema"]["additionalProperties"] is False
    assert tools["press_keys"]["inputSchema"]["required"] == ["keys"]
    assert tools["press_keys"]["inputSchema"]["properties"]["keys"]["type"] == "string"


def test_capture_surface_takes_an_optional_surface_and_reports_provenance(wired):
    """``surface`` became optional; the result can name what/how it captured."""
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}
    schema = tools["capture_surface"]["inputSchema"]

    assert "surface" not in (schema.get("required") or [])
    assert "Omit to capture the live active window" in schema["properties"]["surface"]["description"]
    assert "Fallback" in schema["properties"]["theme"]["description"]
    properties = tools["capture_surface"]["outputSchema"]["properties"]
    for key in (
        "surface",
        "what",
        "path",
        "method",
        "size",
        "rhi_layers",
        "theme",
        "options_applied",
        "unavailable",
    ):
        assert key in properties, key


def test_capture_without_surface_and_no_live_instance_is_refused(wired):
    """No surface is a live-active-window request — never a silent other surface."""
    protocol, _backend, calls = wired
    result = _call(protocol, "capture_surface", {})

    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "surface is required when no live instance is attached" in text
    assert calls["launches"] == [], "a refused capture must not boot anything"


def test_capture_surface_still_rejects_unknown_parameters(wired):
    protocol, _backend, _calls = wired
    response = _request(
        protocol,
        "tools/call",
        {"name": "capture_surface", "arguments": {"what": "settings"}},
        rid=7,
    )
    assert response["error"]["code"] == -32602
    assert "unexpected parameter 'what'" in response["error"]["message"]


# --- evidence probe: capture provenance -------------------------------------

#: Frozen spec id this probe owns (``docs/dev/EVIDENCE.md`` / ADR-008 vocabulary).
CAPTURE_PROVENANCE_SPEC = "spec.mcp.capture_provenance"


class _ScriptedCaptureClient:
    """Live transport stub: one scripted ``capture_live`` answer.

    Faked at ``LiveClient.call`` (never at ``LiveBackend.capture_surface``) so
    the provenance mapping under test runs for real — a stub at the adapter
    level would only restate the mapping it is supposed to measure.
    """

    def __init__(self, answer: dict) -> None:
        self.answer = dict(answer)
        self.requests: list[tuple[str, dict]] = []

    def alive(self) -> bool:
        return True

    def call(self, method, params=None, *, retry_on_timeout=False):
        self.requests.append((method, dict(params or {})))
        return dict(self.answer)

    def close(self) -> None:
        return None


def _derived_provenance(payload: dict) -> tuple[bool, str]:
    """``(complete, signal)`` derived from a capture payload, never the request.

    "Complete" means the payload really carries what was grabbed
    (``what``), how (``method``), a non-negative ``rhi_layers`` and a two-int
    ``size``, and reports nothing in ``unavailable``. Anything less is a miss
    whose signal names the fields, which is what makes the verdict falsifiable.
    """
    what = payload.get("what")
    method = payload.get("method")
    layers = payload.get("rhi_layers")
    size = payload.get("size")
    missing = [str(name) for name in payload.get("unavailable") or ()]
    complete = bool(
        what
        and method
        and isinstance(layers, int)
        and layers >= 0
        and isinstance(size, list)
        and len(size) == 2
        and all(isinstance(edge, int) for edge in size)
        and not missing
    )
    if complete:
        return True, f"what={what}; method={method}; rhi_layers={layers}; size={size}"
    return False, f"unavailable={','.join(missing) or 'provenance-missing'}"


def test_evidence_capture_provenance_is_kept_and_never_invented(
    wired, monkeypatch, tmp_path
):
    """``spec.mcp.capture_provenance``: a capture names what/how it grabbed.

    Requirement (``docs/dev/MCP.md`` § *Capture provenance*): a live result
    keeps the app's ``what`` / ``method`` / ``size`` / ``rhi_layers``; the
    fallback path lists ``method`` and ``rhi_layers`` as unavailable rather
    than inventing values.

    Falsification — the verdict is derived from the payloads, so drift is red:

    * the live answer goes through the *real* ``LiveBackend.capture_surface``
      with only ``LiveClient.call`` scripted, so a mapping that drops or
      renames a provenance field is measured instead of restated;
    * a second live answer with the app-side provenance stripped must flip the
      same derivation to "missing" (``unavailable`` naming the fields) — the
      probe cannot go green on a payload that carries nothing;
    * the fallback capture fakes only the devtool subprocess and must both
      parse its own size and list exactly the two unknowable fields.

    Runs offscreen only — no Xvfb (the supervisor runs the live proof).
    """
    protocol, backend, _calls = wired
    reset_journal()

    full = {
        "what": "settings",
        "path": str(tmp_path / "live.png"),
        "size": [1440, 900],
        "method": "grabWindow",
        "rhi_layers": 2,
    }
    client = _ScriptedCaptureClient(full)
    backend.live = LiveBackend(client=client)
    live = _call(protocol, "capture_surface", {"surface": "settings"})["structuredContent"]

    # Negative control: same adapter, app answering without provenance.
    backend.live = LiveBackend(client=_ScriptedCaptureClient({"what": "settings"}))
    stripped = _call(protocol, "capture_surface", {"surface": "settings"})[
        "structuredContent"
    ]

    # Fallback: the fixture pins an empty control dir, so no instance attaches.
    import app.backend as backend_module

    backend.live = LiveBackend()
    png = tmp_path / "settings.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")  # content irrelevant; existence is not

    class _Saved:
        returncode = 0
        stdout = f"saved {png} 800x600\n"
        stderr = ""

    monkeypatch.setattr(backend_module.subprocess, "run", lambda *a, **k: _Saved())
    fallback = _call(protocol, "capture_surface", {"surface": "settings"})[
        "structuredContent"
    ]

    live_ok, live_signal = _derived_provenance(live)
    stripped_ok, stripped_signal = _derived_provenance(stripped)
    fallback_ok, fallback_signal = _derived_provenance(fallback)
    fallback_missing = ",".join(fallback.get("unavailable") or ())
    ok = live_ok and not stripped_ok and not fallback_ok

    record_evidence(
        CAPTURE_PROVENANCE_SPEC,
        kind="spec",
        verdict="ok" if ok else "violated",
        signal=f"{live_signal}; fallback_unavailable={fallback_missing}",
        reason=(
            "live capture kept what/method/size/rhi_layers and the fallback "
            "named the fields it cannot know"
            if ok
            else "capture payload lost provenance it reported holding, or "
            "invented a value it could not observe"
        ),
        ids=("settings",),
        area="mcp.capture",
    )

    record = verdict(None, CAPTURE_PROVENANCE_SPEC)
    assert record is not None, "capture-provenance probe emitted no evidence"

    # Assert AFTER emitting, so a failure reads as evidence, not a bare assert.
    assert client.requests == [("capture_live", {"what": "settings"})], (
        "the live adapter must send only 'what' (theme/out are fallback-only)"
    )
    assert live["source"] == "live"
    assert live["method"] == "grabWindow" and live["rhi_layers"] == 2, live
    assert live["size"] == [1440, 900] and live["unavailable"] == [], live
    assert live["what"] == "settings" and live["theme"] is None, live

    assert stripped["unavailable"] == ["method", "size", "rhi_layers"], stripped
    assert not stripped_ok, stripped_signal

    assert fallback["source"] == "fallback" and fallback["what"] == "settings", fallback
    assert fallback["size"] == [800, 600], fallback
    assert fallback["method"] is None and fallback["rhi_layers"] is None, fallback
    assert fallback["unavailable"] == ["method", "rhi_layers"], fallback

    assert ok, (
        f"spec.mcp.capture_provenance violated — live={live_signal}; "
        f"stripped={stripped_signal}; fallback={fallback_signal}"
    )
    assert record.verdict == "ok", record.signal


def test_read_and_write_tools_do_not_mix_annotations(wired):
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}

    for name in ("list_actions", "list_sessions", "get_state", "read_log", "query_trace",
                 "dump_ui_layout", "list_surfaces", "ui_elements", "jobs_list", "wait_for"):
        annotations = tools[name]["annotations"]
        assert annotations["readOnlyHint"] is True, name
        assert annotations["destructiveHint"] is False, name

    for name in ("open_tab", "run_action", "open_folder", "set_theme", "set_language",
                 "capture_surface", "press_keys", "ui_click", "ui_hover", "ui_focus",
                 "jobs_cancel"):
        assert tools[name]["annotations"]["readOnlyHint"] is False, name
    assert tools["run_action"]["annotations"]["destructiveHint"] is True
    # Injecting input is not destructive, but is not idempotent either.
    assert tools["press_keys"]["annotations"]["destructiveHint"] is False
    assert tools["press_keys"]["annotations"]["idempotentHint"] is False
    for tool in tools.values():
        assert tool["annotations"]["openWorldHint"] is False, tool["name"]


def test_element_tool_annotations_are_audited(wired):
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}

    assert tools["ui_elements"]["annotations"]["readOnlyHint"] is True
    assert tools["ui_click"]["annotations"]["readOnlyHint"] is False
    assert tools["ui_click"]["annotations"]["destructiveHint"] is False
    assert tools["ui_click"]["annotations"]["idempotentHint"] is False
    assert tools["ui_hover"]["annotations"]["idempotentHint"] is True
    assert tools["ui_focus"]["annotations"]["idempotentHint"] is True
    assert tools["ui_elements"]["inputSchema"]["additionalProperties"] is False
    assert tools["ui_click"]["inputSchema"]["required"] == ["id"]
    assert tools["ui_click"]["inputSchema"]["properties"]["button"]["enum"] == [
        "left",
        "right",
        "middle",
    ]


def test_ui_elements_catalog_declares_filters_and_properties(wired):
    """Narrowing happens server-side; each row carries a serialisable bag."""
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}
    schema = tools["ui_elements"]["inputSchema"]["properties"]

    assert schema["role"]["type"] == "string"
    assert schema["label"]["type"] == "string"
    assert schema["properties"]["type"] == "object"
    assert schema["limit"]["type"] == "integer"
    assert schema["limit"]["maximum"] == 2000
    assert schema["limit"]["minimum"] == 1

    element = tools["ui_elements"]["outputSchema"]["properties"]["elements"]["items"]
    assert element["properties"]["properties"]["type"] == "object"
    assert {"id", "properties"} <= set(element.get("required") or ())

    surfaces = tools["list_surfaces"]["outputSchema"]["properties"]["surfaces"]["items"]
    assert surfaces["properties"]["live"]["type"] == "boolean"
    assert surfaces["properties"]["capturable"]["type"] == "boolean"



def test_job_tool_annotations_are_audited(wired):
    """``jobs_list`` reads; ``jobs_cancel`` mutates without pretending safety."""
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}

    assert tools["jobs_list"]["annotations"]["readOnlyHint"] is True
    assert tools["jobs_list"]["annotations"]["destructiveHint"] is False
    assert tools["jobs_cancel"]["annotations"]["readOnlyHint"] is False
    # Cancelling kills in-flight work: not destructive to user files, but not
    # repeatable either (a settled id is an error).
    assert tools["jobs_cancel"]["annotations"]["destructiveHint"] is False
    assert tools["jobs_cancel"]["annotations"]["idempotentHint"] is False
    assert tools["jobs_cancel"]["inputSchema"]["required"] == ["id"]
    assert tools["jobs_list"]["inputSchema"]["additionalProperties"] is False
    job = tools["jobs_list"]["outputSchema"]["properties"]["jobs"]["items"]
    assert job["properties"]["kind"]["enum"] == list(catalog.JOB_KINDS)
    assert job["properties"]["status"]["enum"] == list(catalog.JOB_STATUSES)
    assert {"id", "kind", "status", "message"} <= set(job.get("required") or ())
    assert tools["jobs_cancel"]["outputSchema"]["properties"]["kind"]["enum"] == list(
        catalog.CANCELLABLE_JOB_KINDS
    )


def test_list_actions_output_schema_declares_enabled_and_reason(wired):
    """The catalog publishes the P2 ``enabled``/``reason`` row keys."""
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}
    item = tools["list_actions"]["outputSchema"]["properties"]["actions"]["items"]
    assert item["properties"]["enabled"]["type"] == "boolean"
    assert item["properties"]["reason"]["type"] == ["string", "null"]
    assert {"enabled", "reason"} <= set(item.get("required") or ())


def test_list_actions_fallback_rows_carry_enabled_and_reason(wired):
    """Every fallback row carries the two keys even when the snapshot omits them."""
    protocol, _backend, _calls = wired
    rows = _call(protocol, "list_actions")["structuredContent"]["actions"]
    assert rows, "the registry snapshot must list platform actions"
    for row in rows:
        assert row["enabled"] is True
        assert row["reason"] is None


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


# --- fallback safety: display policy, process reuse, log preservation -------


def test_launch_env_defaults_to_headless_and_scrubs_the_session(monkeypatch):
    """Regression guard (defect 2): a fallback boot must not inherit DISPLAY."""
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("IMGSLI_MCP_DISPLAY", raising=False)

    env = launch_env()
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE"):
        assert key not in env


def test_launch_env_visible_uses_the_opted_in_private_display(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("IMGSLI_MCP_DISPLAY", ":97")

    env = launch_env(visible=True)
    assert env["DISPLAY"] == ":97", "the opt-in display wins over the session's"
    assert env["QT_QPA_PLATFORM"] == "xcb"
    assert "WAYLAND_DISPLAY" not in env and "XDG_SESSION_TYPE" not in env


def test_launch_env_visible_without_opt_in_stays_headless(monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("IMGSLI_MCP_DISPLAY", raising=False)

    env = launch_env(visible=True)
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    assert "DISPLAY" not in env


def test_fallback_launch_env_is_headless_on_a_wayland_session(wired, monkeypatch):
    _protocol, backend, _calls = wired
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("IMGSLI_MCP_DISPLAY", raising=False)

    env = backend._launch_env()
    assert env["QT_QPA_PLATFORM"] == "offscreen"
    assert "DISPLAY" not in env and "WAYLAND_DISPLAY" not in env
    assert env["PYTHONPATH"].startswith(str(REPO_ROOT / "src"))


def test_process_registry_keeps_only_live_pids():
    registry = ProcessRegistry()
    registry.adopt("image_compare", os.getpid())
    assert registry.live_pid("image_compare") == os.getpid()

    registry.adopt("multi_compare", 2**30)
    assert registry.live_pid("multi_compare") is None, "a dead pid is dropped, not returned"
    assert registry.live_pid("multi_compare") is None

    registry.release("image_compare")
    assert registry.live_pid("image_compare") is None
    assert pid_alive(os.getpid()) is True
    assert pid_alive(2**30) is False
    assert pid_alive(None) is False and pid_alive(0) is False


def test_preserve_live_log_copies_the_log_before_a_boot_clobbers_it(tmp_path):
    source = tmp_path / "data" / "log.txt"
    source.parent.mkdir(parents=True)
    source.write_text("live line\n", encoding="utf-8")

    preserved = preserve_live_log(tmp_path / "artifacts", source=source)
    assert preserved == str(tmp_path / "artifacts" / PRESERVED_LOG_NAME)
    assert Path(preserved).read_text(encoding="utf-8") == "live line\n"
    assert preserve_live_log(tmp_path / "artifacts", source=tmp_path / "absent.txt") is None


def test_open_tab_reuses_a_live_fallback_process(wired):
    protocol, backend, calls = wired
    backend.processes.adopt("image_compare", os.getpid())

    result = _call(protocol, "open_tab", {"tab": "image_compare"})
    structured = result["structuredContent"]
    assert structured["reused"] is True
    assert structured["launched"] is False
    assert structured["pid"] == os.getpid()
    assert structured["source"] == "fallback"
    assert calls["launches"] == [], "a tab with a live process must not spawn a second one"


def test_open_tab_spawns_again_when_the_tracked_process_is_gone(wired):
    protocol, backend, calls = wired
    backend.processes.adopt("image_compare", 2**30)

    result = _call(protocol, "open_tab", {"tab": "image_compare"})
    assert result["structuredContent"]["launched"] is True
    assert result["structuredContent"]["pid"] == 4242
    assert calls["launches"] == [["--open-tab", "image_compare"]]


def test_press_keys_without_a_live_instance_errors_honestly(wired):
    protocol, _backend, calls = wired
    result = _call(protocol, "press_keys", {"keys": "ctrl+p"})
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "no live instance" in text
    assert "keyboard input needs a running app" in text
    assert "structuredContent" not in result
    assert calls["launches"] == [] and calls["tabs"] == [], "no fake keys, no headless boot"


@pytest.mark.parametrize(
    "tool,arguments",
    [
        ("ui_elements", {}),
        ("ui_click", {"id": "main.settings.btn"}),
        ("ui_hover", {"id": "main.settings.btn"}),
        ("ui_focus", {"id": "main.settings.btn"}),
    ],
)
def test_element_tools_without_a_live_instance_error_honestly(wired, monkeypatch, tool, arguments):
    """Element targeting is live-only: no instance ⇒ honest error, no process."""
    protocol, _backend, calls = wired
    import app.backend as backend_module

    spawned: list = []
    monkeypatch.setattr(backend_module.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(backend_module.subprocess, "run", lambda *a, **k: spawned.append(a))

    result = _call(protocol, tool, arguments)
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "no live instance" in text
    assert "running app" in text
    assert "structuredContent" not in result
    assert spawned == [], "element targeting must never spawn a process"
    assert calls["launches"] == [] and calls["tabs"] == [], "no fake action, no headless boot"


@pytest.mark.parametrize(
    "tool,arguments",
    [("jobs_list", {}), ("jobs_cancel", {"id": "export:multi_compare:3"})],
)
def test_job_tools_without_a_live_instance_error_honestly(wired, monkeypatch, tool, arguments):
    """Job state is live-only: no instance ⇒ honest error, never a fake empty list."""
    protocol, _backend, calls = wired
    import app.backend as backend_module

    spawned: list = []
    monkeypatch.setattr(backend_module.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(backend_module.subprocess, "run", lambda *a, **k: spawned.append(a))

    result = _call(protocol, tool, arguments)
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "no live instance" in text
    assert "job state needs a running app" in text
    assert "structuredContent" not in result
    assert spawned == [], "job reporting must never spawn a process"
    assert calls["launches"] == [] and calls["tabs"] == [], "no headless boot for job state"


# --- wait_for (live-only, one selector per call) ----------------------------


class _ScriptedLive:
    """``LiveBackend`` stand-in: one scripted observation per poll.

    Frames are returned in order and the last one repeats, so a predicate that
    only becomes true on the n-th observation is deterministic without a real
    app or a display. Each poll is timestamped, letting a test prove
    ``waited_ms`` covers the window it actually observed.
    """

    def __init__(self, frames):
        self.frames = [list(frame) for frame in frames]
        self.polls: list[tuple[str, float]] = []
        self.returned: list[list] = []
        self.include_disabled: list[bool | None] = []
        self.failures = 0

    def client_if_alive(self):
        return object()

    def note_failure(self):
        self.failures += 1

    def _frame(self, label):
        self.polls.append((label, time.monotonic()))
        index = min(len(self.returned), len(self.frames) - 1)
        frame = self.frames[index]
        self.returned.append(frame)
        return frame

    def ui_elements(self, *, client=None, scope=None, include_disabled=None):
        self.include_disabled.append(include_disabled)
        rows = self._frame("ui_elements")
        return {"count": len(rows), "window_count": 1, "elements": rows, "source": "live"}

    def jobs_list(self, *, client=None):
        rows = self._frame("jobs_list")
        return {"count": len(rows), "jobs": rows, "source": "live"}


def _element_row(id, *, role="button", label="Open", visible=True, enabled=True):
    return {
        "id": id,
        "role": role,
        "label": label,
        "rect": [0, 0, 10, 10],
        "screen_rect": [0, 0, 10, 10],
        "window": "main",
        "owner_tab": None,
        "action_id": None,
        "enabled": enabled,
        "visible": visible,
    }


def _job_row(kind="gallery_pool", id="pool:image_gallery", status="running"):
    return {
        "id": id,
        "kind": kind,
        "status": status,
        "progress": {"done": 1, "total": 4},
        "elapsed_s": 1.0,
        "message": "thumbnails 1/4 loaded",
    }


def test_wait_for_element_resolves_on_a_later_poll(wired):
    protocol, backend, _calls = wired
    row = _element_row("gallery.thumb.3")
    fake = _ScriptedLive([[], [row]])
    backend.live = fake

    result = _call(
        protocol,
        "wait_for",
        {"element": "gallery.thumb.3", "timeout_ms": 2000, "poll_ms": 25},
    )

    structured = result["structuredContent"]
    assert result["isError"] is False
    assert structured["ok"] is True
    assert structured["reason"] is None
    assert structured["predicate"] == {
        "selector": "element",
        "element": "gallery.thumb.3",
        "role": None,
        "label": None,
        "job_kind": None,
    }
    assert structured["observed"] == row == fake.returned[-1][0]
    assert structured["source"] == "live"
    assert [label for label, _stamp in fake.polls] == ["ui_elements", "ui_elements"]
    # Visibility/enabled can only be judged when disabled rows are visible too.
    assert fake.include_disabled == [True, True]


def test_wait_for_element_keeps_waiting_until_it_is_enabled(wired):
    protocol, backend, _calls = wired
    disabled = _element_row("gallery.thumb.9", enabled=False)
    enabled = _element_row("gallery.thumb.9")
    fake = _ScriptedLive([[disabled], [enabled]])
    backend.live = fake

    result = _call(
        protocol,
        "wait_for",
        {"element": "gallery.thumb.9", "timeout_ms": 2000, "poll_ms": 25},
    )

    structured = result["structuredContent"]
    assert structured["ok"] is True
    assert structured["observed"] == enabled
    assert len(fake.polls) == 2, "a present-but-disabled row is not the predicate"


def test_wait_for_role_and_label_matches_the_exact_pair(wired):
    protocol, backend, _calls = wired
    other = _element_row("main.close", role="button", label="Close")
    match = _element_row("main.open", role="toolbar.button", label="Open")
    fake = _ScriptedLive([[other], [other, match]])
    backend.live = fake

    result = _call(
        protocol,
        "wait_for",
        {"role": "toolbar.button", "label": "Open", "timeout_ms": 2000, "poll_ms": 25},
    )

    structured = result["structuredContent"]
    assert structured["ok"] is True
    assert structured["observed"] == match == fake.returned[-1][1]
    assert structured["predicate"]["selector"] == "role_label"
    assert structured["predicate"]["role"] == "toolbar.button"


def test_wait_for_role_and_label_is_case_sensitive(wired):
    protocol, backend, _calls = wired
    fake = _ScriptedLive([[_element_row("main.open", role="button", label="open")]])
    backend.live = fake

    result = _call(
        protocol,
        "wait_for",
        {"role": "button", "label": "Open", "timeout_ms": 60, "poll_ms": 25},
    )

    structured = result["structuredContent"]
    assert structured["ok"] is False
    assert structured["observed"] is None
    assert "role 'button' and label 'Open'" in structured["hint"]


def test_wait_for_job_settled_sees_the_running_row_disappear(wired):
    protocol, backend, _calls = wired
    running = _job_row()
    fake = _ScriptedLive([[running], [running], []])
    backend.live = fake

    result = _call(
        protocol, "wait_for", {"job_settled": True, "timeout_ms": 2000, "poll_ms": 25}
    )

    structured = result["structuredContent"]
    assert structured["ok"] is True
    assert structured["observed"] == []
    assert structured["predicate"]["selector"] == "job_settled"
    assert len(fake.polls) == 3, "a listed row is not settled until it disappears"


def test_wait_for_job_settled_honours_job_kind(wired):
    protocol, backend, _calls = wired
    fake = _ScriptedLive([[_job_row(kind="metrics_pass", id="metrics:image_gallery")]])
    backend.live = fake

    result = _call(
        protocol,
        "wait_for",
        {"job_settled": True, "job_kind": "export", "timeout_ms": 2000, "poll_ms": 25},
    )

    structured = result["structuredContent"]
    assert structured["ok"] is True, "another kind still running must not block an export wait"
    assert structured["observed"] == []
    assert structured["predicate"]["job_kind"] == "export"


def test_wait_for_timeout_returns_the_last_observed_row(wired):
    protocol, backend, _calls = wired
    disabled = _element_row("gallery.thumb.9", enabled=False)
    fake = _ScriptedLive([[disabled]])
    backend.live = fake

    started = time.monotonic()
    result = _call(
        protocol,
        "wait_for",
        {"element": "gallery.thumb.9", "timeout_ms": 80, "poll_ms": 25},
    )
    elapsed_ms = (time.monotonic() - started) * 1000

    structured = result["structuredContent"]
    assert result["isError"] is False, "a timeout is a normal result, never a tool error"
    assert structured["ok"] is False
    assert structured["reason"] == "timeout"
    assert structured["observed"] == disabled == fake.returned[-1][0]
    assert structured["hint"] and "enabled=false" in structured["hint"]
    assert structured["source"] == "live"
    assert structured["waited_ms"] >= 80
    assert structured["waited_ms"] <= 80 + 25 + 100
    assert 80 <= elapsed_ms <= 80 + 25 + 250
    stamps = [stamp for _label, stamp in fake.polls]
    assert stamps == sorted(stamps), "poll observations must be monotonic"
    assert structured["waited_ms"] >= (stamps[-1] - stamps[0]) * 1000


def test_wait_for_element_timeout_suggests_close_ids(wired):
    protocol, backend, _calls = wired
    fake = _ScriptedLive([[_element_row("gallery.thumb.30")]])
    backend.live = fake

    result = _call(
        protocol,
        "wait_for",
        {"element": "gallery.thumb.3", "timeout_ms": 50, "poll_ms": 25},
    )

    structured = result["structuredContent"]
    assert structured["ok"] is False
    assert structured["observed"] is None
    assert "did you mean: gallery.thumb.30" in structured["hint"]


@pytest.mark.parametrize(
    "arguments,fragment",
    [
        ({}, "exactly one predicate selector"),
        ({"element": "main.settings.btn", "role": "button", "label": "Open"},
         "exactly one predicate selector"),
        ({"element": "main.settings.btn", "job_settled": True},
         "exactly one predicate selector"),
        ({"role": "button"}, "role and label must be passed together"),
        ({"job_kind": "export"}, "only applies with job_settled=true"),
        ({"job_settled": False}, "job_settled must be true"),
        ({"element": "   "}, "non-empty element id"),
    ],
)
def test_wait_for_selector_validation_is_named(wired, arguments, fragment):
    protocol, _backend, calls = wired
    result = _call(protocol, "wait_for", arguments)

    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert fragment in text
    assert "Hint:" in text
    assert "structuredContent" not in result
    assert calls["launches"] == [] and calls["tabs"] == []


@pytest.mark.parametrize(
    "arguments,fragment",
    [
        ({"element": "main.settings.btn", "timeout_ms": -5}, ">= 1"),
        ({"element": "main.settings.btn", "timeout_ms": 60001}, "<= 60000"),
        ({"element": "main.settings.btn", "poll_ms": 24}, ">= 25"),
    ],
)
def test_wait_for_bounds_are_protocol_validation_errors(wired, arguments, fragment):
    protocol, _backend, _calls = wired
    response = _request(
        protocol, "tools/call", {"name": "wait_for", "arguments": arguments}, rid=11
    )

    assert response["error"]["code"] == -32602
    assert fragment in response["error"]["message"]
    assert "timeout_ms" in response["error"]["message"] or "poll_ms" in response["error"]["message"]


def test_wait_for_handler_refuses_out_of_schema_bounds_directly(wired):
    """A direct handler call (no protocol layer) still validates its budget."""
    from app.backend import ToolError

    _protocol, backend, _calls = wired
    with pytest.raises(ToolError, match="timeout_ms must be >= 1"):
        backend.wait_for(element="main.settings.btn", timeout_ms=0)


def test_wait_for_without_a_live_instance_errors_honestly(wired, monkeypatch):
    """No instance ⇒ the standard live-only refusal, never a silent timeout."""
    protocol, _backend, calls = wired
    import app.backend as backend_module

    spawned: list = []
    monkeypatch.setattr(backend_module.subprocess, "Popen", lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(backend_module.subprocess, "run", lambda *a, **k: spawned.append(a))

    started = time.monotonic()
    result = _call(protocol, "wait_for", {"element": "main.settings.btn"})
    elapsed = time.monotonic() - started

    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "no live instance" in text
    assert "waiting for app state needs a running app" in text
    assert "structuredContent" not in result
    assert elapsed < 1.0, "the refusal must not spend the default wait budget"
    assert spawned == [], "waiting must never spawn a process"
    assert calls["launches"] == [] and calls["tabs"] == []


def test_wait_for_catalog_declares_one_selector_and_readonly(wired):
    protocol, _backend, _calls = wired
    tools = {tool["name"]: tool for tool in _request(protocol, "tools/list")["result"]["tools"]}
    tool = tools["wait_for"]

    assert tool["annotations"]["readOnlyHint"] is True
    assert tool["annotations"]["destructiveHint"] is False
    assert tool["annotations"]["idempotentHint"] is True
    assert "required" not in tool["inputSchema"], "the one-of rule is cross-field, not required[]"
    props = tool["inputSchema"]["properties"]
    assert props["timeout_ms"]["default"] == 5000
    assert props["timeout_ms"]["maximum"] == 60000
    assert props["poll_ms"]["default"] == 100
    assert props["poll_ms"]["minimum"] == 25
    assert props["job_kind"]["enum"] == list(catalog.JOB_KINDS)
    output = tool["outputSchema"]
    assert output["properties"]["source"]["enum"] == ["live"]
    assert {"ok", "waited_ms", "predicate", "observed", "source"} <= set(output["required"])


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
        assert structured["source"] == "fallback", name


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


def test_stdio_refuses_an_oversized_request_line(wired):
    """A request line over the P2 cap is a named error, never truncated."""
    protocol, _backend, _calls = wired
    oversized = "x" * (MAX_REQUEST_LINE_BYTES + 1)
    out = io.StringIO()
    code = serve_stdio(protocol, stdin=io.StringIO(oversized + "\n"), stdout=out)
    assert code == 0
    entry = json.loads(out.getvalue().strip())
    assert entry["error"]["code"] == INVALID_REQUEST
    assert "cap" in entry["error"]["message"]


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
