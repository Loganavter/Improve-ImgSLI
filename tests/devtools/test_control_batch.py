"""``ui_batch`` — an ordered batch of the single-action verbs (MCP).

Why this exists: building a stand or driving a form cost one agent turn (and
one round trip) per click. The batch is a loop over *already published* verbs,
not a second dispatch surface — each item calls the same bound method the
single tool uses, so live/fallback routing, argument validation and error
shapes are not duplicated.

Falsification: on the pre-change tree neither ``catalog.ui_batch`` nor
``AppBackend.ui_batch`` exists, so every test here fails at import/attribute
resolution before reaching an assertion (proven RED).

Contract points covered:

* (a) items run in order and report per-item results;
* (b) the default stops at the first failure — later items did not run;
* (c) ``stop_on_error=false`` runs the rest and still reports the first error;
* (d) an unknown tool, an unknown key, a missing required key and nesting are
  refused *before* anything runs, with the allowed list in the hint;
* (e) a sub-tool ``ToolError`` is reported as ``tool_error``; a crash as
  ``crashed`` — a batch never re-raises a sub-item failure;
* (f) ``settle_ms`` sleeps between items, never after the last one, and the
  accumulated budget is refused up front;
* (g) the catalog enum, the whitelist and the backend methods cannot drift.

Runs offscreen only; no live instance is attached (discovery is pinned empty).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from app import backend as backend_module  # noqa: E402
from app import catalog  # noqa: E402
from app.backend import AppBackend, ToolError  # noqa: E402
from app.protocol import MCPProtocol  # noqa: E402


@pytest.fixture
def backend(tmp_path, monkeypatch):
    """A backend with discovery pinned empty — it can never attach a real app."""
    monkeypatch.delenv("IMGSLI_MCP_CONTROL_SOCKET", raising=False)
    monkeypatch.setenv("IMGSLI_CONTROL_DIR", str(tmp_path / "no-instance"))
    return AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
    )


def _recorder(calls, name, result=None):
    def call(**kwargs):
        calls.append((name, kwargs))
        return result if result is not None else {"ok": True, "source": "live"}

    return call


def test_items_run_in_order_and_report_their_results(backend, monkeypatch):
    calls: list = []
    monkeypatch.setattr(backend, "ui_click", _recorder(calls, "click"))
    monkeypatch.setattr(backend, "ui_hover", _recorder(calls, "hover"))

    out = backend.ui_batch(
        actions=[
            {"tool": "ui_click", "arguments": {"id": "palette.a"}},
            {"tool": "ui_hover", "arguments": {"id": "palette.b"}},
            {"tool": "ui_click", "arguments": {"id": "palette.c"}},
        ]
    )

    assert out["ok"] is True
    assert out["count"] == 3
    assert out["ok_count"] == 3
    assert out["stopped_at"] is None
    assert out["error"] is None
    assert [c[1]["id"] for c in calls] == ["palette.a", "palette.b", "palette.c"]
    assert [row["index"] for row in out["results"]] == [0, 1, 2]
    assert all(row["ok"] and row["error"] is None for row in out["results"])
    assert out["source"] == "live"


def test_a_failure_stops_the_batch_by_default(backend, monkeypatch):
    calls: list = []

    def boom(**kwargs):
        calls.append(("boom", kwargs))
        raise ToolError("element vanished", "call ui_elements again")

    monkeypatch.setattr(backend, "ui_click", _recorder(calls, "click"))
    monkeypatch.setattr(backend, "ui_hover", boom)

    out = backend.ui_batch(
        actions=[
            {"tool": "ui_click", "arguments": {"id": "a"}},
            {"tool": "ui_hover", "arguments": {"id": "b"}},
            {"tool": "ui_click", "arguments": {"id": "c"}},
        ]
    )

    assert out["ok"] is False
    assert out["count"] == 2, "the third item did not run"
    assert out["ok_count"] == 1
    assert out["stopped_at"] == 1
    assert out["error"]["kind"] == "tool_error"
    assert out["error"]["message"] == "element vanished"
    assert out["error"]["hint"] == "call ui_elements again"
    assert [c[1]["id"] for c in calls] == ["a", "b"], "no item after the failure"


def test_stop_on_error_false_runs_the_rest_and_keeps_the_first_error(backend, monkeypatch):
    calls: list = []

    def boom(**kwargs):
        calls.append(("boom", kwargs))
        raise ToolError("first failure", None)

    monkeypatch.setattr(backend, "ui_click", boom)
    monkeypatch.setattr(backend, "ui_hover", _recorder(calls, "hover"))

    out = backend.ui_batch(
        actions=[
            {"tool": "ui_click", "arguments": {"id": "a"}},
            {"tool": "ui_hover", "arguments": {"id": "b"}},
        ],
        stop_on_error=False,
    )

    assert out["ok"] is False
    assert out["count"] == 2
    assert out["ok_count"] == 1
    assert out["stopped_at"] == 0
    assert out["error"]["message"] == "first failure"
    assert calls[-1] == ("hover", {"id": "b"})


def test_a_crash_is_reported_not_re_raised(backend, monkeypatch):
    def crash(**kwargs):
        raise RuntimeError("handler exploded")

    monkeypatch.setattr(backend, "ui_click", crash)

    out = backend.ui_batch(actions=[{"tool": "ui_click", "arguments": {"id": "a"}}])

    assert out["ok"] is False
    assert out["error"]["kind"] == "crashed"
    assert "RuntimeError" in out["error"]["message"]


@pytest.mark.parametrize(
    "item, needle",
    [
        ({"tool": "definitely_not_a_tool", "arguments": {}}, "allowed: "),
        ({"tool": "ui_click", "arguments": {"id": "a", "bogus": 1}}, "does not take: bogus"),
        ({"tool": "ui_click", "arguments": {}}, "missing required argument"),
        ({"tool": "ui_click", "arguments": "id=a"}, "must be an object"),
        ({"tool": "ui_batch", "arguments": {"actions": []}}, "allowed: "),
        ("not-an-object", "is not an object"),
    ],
)
def test_invalid_items_are_refused_before_anything_runs(backend, monkeypatch, item, needle):
    calls: list = []
    monkeypatch.setattr(backend, "ui_click", _recorder(calls, "click"))

    out = backend.ui_batch(actions=[item])

    assert out["ok"] is False
    assert out["ok_count"] == 0
    assert calls == []
    assert out["error"]["kind"] == "invalid_item"
    assert needle in out["error"]["hint"] or needle in out["error"]["message"]


def test_nesting_is_refused_and_the_whitelist_is_named(backend):
    out = backend.ui_batch(
        actions=[{"tool": "ui_batch", "arguments": {"actions": [{"tool": "ui_click"}]}}]
    )
    assert out["error"]["kind"] == "invalid_item"
    assert "unknown batch tool" in out["error"]["message"]
    assert "ui_click" in out["error"]["hint"], "the allowed list is in the hint"
    assert "ui_batch" not in catalog.BATCH_TOOLS


def test_settle_happens_between_items_never_after_the_last(backend, monkeypatch):
    calls: list = []
    sleeps: list = []
    monkeypatch.setattr(backend, "ui_click", _recorder(calls, "click"))
    monkeypatch.setattr(backend_module.time, "sleep", lambda s: sleeps.append(s))

    out = backend.ui_batch(
        actions=[{"tool": "ui_click", "arguments": {"id": str(i)}} for i in range(3)],
        settle_ms=7,
    )

    assert out["ok"] is True
    assert sleeps == [0.007, 0.007]


def test_the_accumulated_settle_budget_is_refused_up_front(backend, monkeypatch):
    calls: list = []
    monkeypatch.setattr(backend, "ui_click", _recorder(calls, "click"))

    with pytest.raises(ToolError) as caught:
        backend.ui_batch(
            actions=[{"tool": "ui_click", "arguments": {"id": str(i)}} for i in range(40)],
            settle_ms=1000,
        )

    assert "sleep" in caught.value.message
    assert calls == [], "nothing ran before the budget check"


def test_empty_and_oversized_batches_are_refused(backend):
    with pytest.raises(ToolError):
        backend.ui_batch(actions=[])
    with pytest.raises(ToolError) as caught:
        backend.ui_batch(
            actions=[{"tool": "ui_hover", "arguments": {"id": "a"}}]
            * (catalog.MAX_BATCH_ACTIONS + 1)
        )
    assert "at most" in caught.value.message


def test_source_is_mixed_when_the_batch_crossed_both_paths(backend, monkeypatch):
    monkeypatch.setattr(
        backend, "ui_click", _recorder([], "click", result={"source": "live"})
    )
    monkeypatch.setattr(
        backend, "ui_hover", _recorder([], "hover", result={"source": "fallback"})
    )

    out = backend.ui_batch(
        actions=[
            {"tool": "ui_click", "arguments": {"id": "a"}},
            {"tool": "ui_hover", "arguments": {"id": "b"}},
        ]
    )

    assert out["source"] == "mixed"
    assert [row["result"]["source"] for row in out["results"]] == ["live", "fallback"]


def test_the_catalog_whitelist_and_the_backend_methods_cannot_drift(backend):
    tools = {tool["name"]: tool for tool in catalog.TOOLS}
    assert "ui_batch" in tools
    spec = tools["ui_batch"]
    assert spec["handler"] == "ui_batch"
    assert callable(getattr(backend, spec["handler"], None))
    items = spec["inputSchema"]["properties"]["actions"]["items"]
    assert items["properties"]["tool"]["enum"] == sorted(catalog.BATCH_TOOLS)
    assert "ui_batch" not in catalog.BATCH_TOOLS
    for name in catalog.BATCH_TOOLS:
        assert name in tools, f"{name} is batchable but not a published tool"
        assert callable(getattr(backend, name, None)), f"{name} has no backend method"


def test_the_batch_answers_through_the_protocol(backend, monkeypatch):
    calls: list = []
    monkeypatch.setattr(backend, "ui_click", _recorder(calls, "click"))
    protocol = MCPProtocol(backend)

    reply = protocol.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ui_batch",
                "arguments": {
                    "actions": [
                        {"tool": "ui_click", "arguments": {"id": "a"}},
                        {"tool": "ui_click", "arguments": {"id": "b"}},
                    ]
                },
            },
        }
    )

    structured = reply["result"]["structuredContent"]
    assert structured["ok"] is True
    assert structured["count"] == 2
    assert [c[1]["id"] for c in calls] == ["a", "b"]
