"""``devtools.scenario_cost`` — the canonical-loop call probe.

Falsification: the module does not exist on the base commit (import fails). A
probe that counts logical steps instead of wire calls fails the sequence/count
assertions; one that crashes on a missing prerequisite fails the blocked-path
test; one that starts a display or needs an app fails the no-socket test.

The fake client is a recorder that plays scripted replies and records every
wire request, so the exact call sequence and count are asserted, not inferred.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

from devtools import scenario_cost

CARD = {"id": "gallery#0/grid.t0@workspace.image_gallery", "role": "card",
        "visible": True, "enabled": True}
CANVAS = {"id": "gallery#0/quicklook.canvas", "role": "canvas",
          "visible": True, "enabled": True}


class _Recorder:
    """Scripted control client: one reply per call, every call recorded.

    The last reply for a method is sticky, so a poll whose second reply is the
    settled one does not need an entry per extra poll.
    """

    def __init__(self, script: dict[str, list[object]]) -> None:
        self.script = {method: list(replies) for method, replies in script.items()}
        self.calls: list[tuple[str, dict]] = []
        self.closed = False

    def call(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, params or {}))
        replies = self.script.get(method) or []
        if not replies:
            raise AssertionError(f"unscripted wire call: {method} {params}")
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        if isinstance(reply, Exception):
            raise reply
        return reply  # type: ignore[return-value]

    def close(self) -> None:
        self.closed = True

    @property
    def methods(self) -> list[str]:
        return [method for method, _params in self.calls]


def _canonical_script() -> dict[str, list[object]]:
    return {
        "open_tab": [{"tab": "image_gallery", "via": "action"}],
        "open_folder": [{"tab": "image_gallery", "routed": True}],
        # First poll still lists a running pass (the step is not settled yet),
        # the second poll is clear: the fake advances on each call.
        "jobs_list": [
            {"jobs": [{"id": "gallery_pool", "kind": "gallery_pool", "status": "running"}]},
            {"jobs": []},
        ],
        "ui_elements": [{"elements": [CARD]}, {"elements": [CARD, CANVAS]}],
        "ui_click": [{"clicked": True, "id": CARD["id"]}],
        "nav_key": [{"activated": True,
                     "steps": [{"handled": "section:gallery"}, {"handled": "surface"}]}],
        "capture_live": [{"path": "/artifacts/live.png", "method": "screen_grab",
                          "rhi_layers": 1, "size": [800, 600]}],
    }


def _run(script: dict[str, list[object]], tmp_path: Path, **kwargs):
    client = _Recorder(script)
    runner = scenario_cost.ScenarioRunner(
        client, folder=tmp_path, socket_label="fake", poll_ms=1,
        sleep=lambda _seconds: None, **kwargs,
    )
    return client, runner.run()


def test_canonical_sequence_and_wire_call_count(tmp_path):
    client, report = _run(_canonical_script(), tmp_path)
    assert client.methods == [
        "open_tab", "open_folder", "jobs_list", "jobs_list", "ui_elements",
        "ui_click", "ui_elements", "nav_key", "capture_live",
    ]
    assert report.calls == 9, "the two waits cost one poll each on top of six steps"
    assert [step.status for step in report.steps] == ["ok"] * 8
    assert report.capture_provenance == "method+rhi_layers"
    assert report.over_budget is True  # 9 > default target 5: the measured gap
    # Step params are the tool's own shape, not a made-up one.
    assert client.calls[0][1] == {"tab": "image_gallery"}
    assert client.calls[1][1] == {"path": str(tmp_path), "tab": "image_gallery"}
    assert client.calls[4][1] == {"scope": "image_gallery"}
    assert client.calls[5][1] == {"id": CARD["id"]}
    assert client.calls[7][1] == {"keys": "Down,Down"}
    assert client.calls[8][1] == {}


def test_job_settled_polls_until_clear_and_reports_the_poll_count(tmp_path):
    """The predicate is false on the first poll and true on the second.

    The fake advances one scripted reply per call, so this is exactly the
    "ok:false, then ok:true" shape — costed as two wire calls, not one.
    """
    client, report = _run(_canonical_script(), tmp_path)
    step = next(s for s in report.steps if s.name == "wait_for:job_settled")
    assert client.methods.count("jobs_list") == 2, "one more poll after ok:false"
    assert step.status == "ok"
    assert step.wire_calls == 2
    assert "settled after 2 poll(s)" in step.detail


def test_job_settled_timeout_is_blocked_not_a_crash(tmp_path):
    script = _canonical_script()
    script["jobs_list"] = [{"jobs": [{"id": "j", "kind": "gallery_pool",
                                      "status": "running"}]}]
    _client, report = _run(script, tmp_path, wait_timeout_ms=0)
    step = next(s for s in report.steps if s.name == "wait_for:job_settled")
    assert step.status == "blocked"
    assert step.detail.startswith("blocked:job_settled timeout")
    # It kept going: the rest of the loop still ran.
    assert report.steps[-1].name == "capture_surface"
    assert report.steps[-1].status == "ok"


def test_missing_cards_block_the_rest_and_count_only_attempts(tmp_path):
    script = _canonical_script()
    script["jobs_list"] = [{"jobs": []}]
    script["ui_elements"] = [{"elements": [{"id": "gallery/tab.t0", "role": "tab"}]}]
    client, report = _run(script, tmp_path)

    assert client.methods == ["open_tab", "open_folder", "jobs_list", "ui_elements"]
    assert report.calls == 4
    blocked = [step for step in report.steps if step.status == "blocked"]
    assert [step.name for step in blocked] == [
        "ui_elements", "ui_click", "wait_for:element", "nav_key", "capture_surface",
    ]
    by_name = {step.name: step for step in blocked}
    assert by_name["ui_click"].detail == "blocked:no-card-in-ui_elements"
    assert by_name["capture_surface"].wire_calls == 0, "a blocked step issues nothing"


def test_budget_over_is_exit_1_and_prints_the_ratio(tmp_path, capsys):
    # The blocked-path script costs exactly 4 wire calls (one poll settles).
    script = _canonical_script()
    script["jobs_list"] = [{"jobs": []}]
    script["ui_elements"] = [{"elements": []}]
    client = _Recorder(script)
    code = scenario_cost.main(["--folder", str(tmp_path), "--budget", "3"], client=client)
    out = capsys.readouterr().out
    assert code == 1
    assert "calls=4" in out
    assert "budget: 4/<=3" in out
    assert client.closed is True


def test_budget_within_exits_0(tmp_path, capsys):
    script = _canonical_script()
    script["jobs_list"] = [{"jobs": []}]
    script["ui_elements"] = [{"elements": []}]
    client = _Recorder(script)
    code = scenario_cost.main(["--folder", str(tmp_path), "--budget", "5"], client=client)
    out = capsys.readouterr().out
    assert code == 0
    assert "calls=4" in out
    assert "budget: 4/<=5" in out


def test_dry_run_issues_nothing_and_prints_the_plan(tmp_path, capsys):
    client = _Recorder({})
    code = scenario_cost.main(["--dry-run", "--folder", str(tmp_path)], client=client)
    out = capsys.readouterr().out
    assert code == 0
    assert client.calls == [], "a dry run must not touch the wire"
    for name, _method, _plan in scenario_cost.STEP_PLAN:
        assert name in out
    assert scenario_cost.PLAN_ID in out
    assert "dry-run: nothing was sent" in out


def test_no_live_instance_exits_2_with_one_line(tmp_path, capsys):
    env = {"XDG_DATA_HOME": str(tmp_path / "data")}  # no runtime dir, no socket
    code = scenario_cost.main(["--folder", str(tmp_path)], env=env)
    out = capsys.readouterr().out
    assert code == 2
    assert out.strip().splitlines() == [
        "no live instance: no control socket found (start the app with control on)"
    ]


def test_missing_folder_is_refused_by_name(tmp_path, capsys):
    missing = tmp_path / "no-such-demo-folder"
    client = _Recorder({})
    code = scenario_cost.main(["--folder", str(missing)], client=client)
    out = capsys.readouterr().out
    assert code == 2
    assert str(missing) in out
    assert "does not exist" in out
    assert client.calls == []


def test_capture_without_provenance_is_reported_not_hidden(tmp_path, capsys):
    script = _canonical_script()
    script["capture_live"] = [{"path": "/artifacts/live.png"}]
    client = _Recorder(script)
    code = scenario_cost.main(["--folder", str(tmp_path), "--json", "--budget", "20"],
                              client=client)
    payload = json.loads(capsys.readouterr().out)
    capture = next(s for s in payload["steps"] if s["step"] == "capture_surface")
    assert code == 0
    assert capture["status"] == "error"
    assert "missing=method,rhi_layers" in capture["detail"]
    assert payload["provenance"]["capture"] == "incomplete:method,rhi_layers"


def test_help_documents_the_budget_rationale():
    text = scenario_cost._build_parser().format_help()
    assert scenario_cost.PLAN_ID in text
    assert "Budget rationale" in text
    assert "wait_for step polls" in text


def test_discover_socket_honours_the_explicit_env_override(tmp_path):
    path = tmp_path / "control.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(path))
        assert scenario_cost.discover_socket(
            {scenario_cost.SOCKET_OVERRIDE_ENV: str(path)}
        ) == path
    finally:
        server.close()
        path.unlink()
    assert scenario_cost.discover_socket(
        {scenario_cost.SOCKET_OVERRIDE_ENV: str(path)}
    ) is None, "a removed socket node is not a live instance"
