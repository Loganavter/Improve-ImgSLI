"""``devtools.scenario_cost`` — the canonical-loop call probe.

Falsification: the module does not exist on the base commit (import fails). A
probe that counts logical steps instead of wire calls (or conflates the two)
fails the accounting/ratio assertions; one that budgets the transport by
default fails the logical-budget tests; one with a fixed poll interval fails
the backoff test; one that waits for ``role="canvas"`` to detect the Quick Look
overlay fails the nav-state predicate tests; one that crashes on a missing
prerequisite fails the blocked-path test; one that starts a display or needs an
app fails the no-socket test.

The fake client is a recorder that plays scripted replies and records every
wire request, so the exact call sequence and count are asserted, not inferred.
The fake clock advances on ``sleep`` rather than waiting, so backoff schedules
are asserted exactly without spending the timeout wall-clock.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from devtools import scenario_cost

CARD = {"id": "gallery#0/grid.t0@workspace.image_gallery", "role": "card",
        "visible": True, "enabled": True}
#: The Quick Look overlay's *navigation* signal — the section it registers while
#: visible (``nav_key`` reports it as ``section:QuickLookNavSection``). The
#: overlay frame itself carries no role, and its preview canvas is not always a
#: visible+enabled ``canvas`` row, so neither is a reliable open signal.
OVERLAY_NAV_STATE = {
    "sections": [{"section": "QuickLookNavSection", "owner": "QuickLookOverlay"}],
    "overlays": [{"widget": "QuickLookOverlay", "element_id": None}],
}
#: What a *closed* overlay looks like: the section is unregistered on close and
#: no overlay widget is visible.
NO_OVERLAY_NAV_STATE = {"sections": [], "overlays": []}


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
    script = _overlay_script()
    # The overlay is already open on the first poll; the job wait still takes
    # two (running, then clear).
    script["ui_nav_state"] = [OVERLAY_NAV_STATE]
    return script


def _run(script: dict[str, list[object]], tmp_path: Path, **kwargs):
    client = _Recorder(script)
    runner = scenario_cost.ScenarioRunner(
        client, folder=tmp_path, socket_label="fake", poll_ms=1,
        sleep=lambda _seconds: None, **kwargs,
    )
    return client, runner.run()


def _overlay_script() -> dict[str, list[object]]:
    """The loop with the overlay wait resolved through ``ui_nav_state``.

    ``jobs_list`` and ``ui_nav_state`` each get two replies (miss, then hit) so
    the wait costs two polls; ``ui_elements`` is read once, for the card.
    """
    return {
        "open_tab": [{"tab": "image_gallery", "via": "action"}],
        "open_folder": [{"tab": "image_gallery", "routed": True}],
        "jobs_list": [
            {"jobs": [{"id": "gallery_pool", "kind": "gallery_pool", "status": "running"}]},
            {"jobs": []},
        ],
        "ui_elements": [{"elements": [CARD]}],
        "ui_click": [{"clicked": True, "id": CARD["id"]}],
        "ui_nav_state": [NO_OVERLAY_NAV_STATE, OVERLAY_NAV_STATE],
        "nav_key": [{"activated": True,
                     "steps": [{"handled": "section:QuickLookNavSection"}]}],
        "capture_live": [{"path": "/artifacts/live.png", "method": "screen_grab",
                          "rhi_layers": 1, "size": [800, 600]}],
    }


class _Clock:
    """A monotonic clock a fake ``sleep`` advances (never a real wall wait)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_canonical_sequence_and_wire_call_count(tmp_path):
    client, report = _run(_canonical_script(), tmp_path)
    assert client.methods == [
        "open_tab", "open_folder", "jobs_list", "jobs_list", "ui_elements",
        "ui_click", "ui_nav_state", "nav_key", "capture_live",
    ]
    assert report.calls == 9, "the job wait costs one poll on top of seven steps"
    assert [step.status for step in report.steps] == ["ok"] * 8
    assert report.logical_steps == 8
    assert report.capture_provenance == "method+rhi_layers"
    assert report.over_budget is True  # 8 logical steps > default target 5
    # Step params are the tool's own shape, not a made-up one.
    assert client.calls[0][1] == {"tab": "image_gallery"}
    assert client.calls[1][1] == {"path": str(tmp_path), "tab": "image_gallery"}
    assert client.calls[4][1] == {"scope": "image_gallery"}
    assert client.calls[5][1] == {"id": CARD["id"]}
    assert client.calls[6][1] == {}
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
        "ui_elements", "ui_click", "wait_for:overlay", "nav_key", "capture_surface",
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
    assert "wire_calls=4" in out
    assert "logical_steps=8" in out
    assert "logical budget: 8/<=3 EXCEEDED" in out
    assert client.closed is True


def test_budget_within_exits_0(tmp_path, capsys):
    script = _canonical_script()
    script["jobs_list"] = [{"jobs": []}]
    script["ui_elements"] = [{"elements": []}]
    client = _Recorder(script)
    code = scenario_cost.main(["--folder", str(tmp_path), "--budget", "8"], client=client)
    out = capsys.readouterr().out
    assert code == 0
    assert "wire_calls=4" in out
    assert "logical budget: 8/<=8" in out


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
    assert "logical_steps" in text and "wire_calls" in text
    assert "--wire-budget" in text
    assert "wait_for poll" in text


# -- logical steps vs wire calls (measured 8 vs 280 on a live instance) ------


def test_report_counts_logical_steps_and_wire_calls_separately(tmp_path, capsys):
    client, report = _run(_overlay_script(), tmp_path)
    # Eight declared steps; the two waits poll twice each on top of the six
    # one-request steps: the gap the live run measured (8 vs 280) is real.
    assert report.logical_steps == 8
    assert report.wire_calls == 10
    assert report.calls == 10, "calls stays the wire count it always was"
    assert report.ratio == 1.25
    assert client.methods == [
        "open_tab", "open_folder", "jobs_list", "jobs_list", "ui_elements",
        "ui_click", "ui_nav_state", "ui_nav_state", "nav_key", "capture_live",
    ]
    runner_report = report.to_dict()
    assert runner_report["logical_steps"] == 8
    assert runner_report["wire_calls"] == 10
    text = scenario_cost.format_summary(report)
    assert "logical_steps=8" in text
    assert "wire_calls=10" in text
    assert "ratio=1.25" in text


def test_budget_fails_on_logical_steps_only_by_default(tmp_path, capsys):
    """10 wire calls under a logical budget of 8 is a pass: the plan's unit is
    tool calls, and the logical count is 8 regardless of how many polls it took.
    """
    client = _Recorder(_overlay_script())
    code = scenario_cost.main(["--folder", str(tmp_path), "--budget", "8",
                               "--poll-ms", "1"], client=client)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "logical_steps=8" in out
    assert "wire_calls=10" in out
    assert "logical budget: 8/<=8" in out
    assert "wire budget" not in out, "no wire budget was asked for"


def test_budget_over_logical_steps_is_exit_1(tmp_path, capsys):
    client = _Recorder(_overlay_script())
    code = scenario_cost.main(["--folder", str(tmp_path), "--budget", "5",
                               "--poll-ms", "1"], client=client)
    out = capsys.readouterr().out
    assert code == 1
    assert "logical budget: 8/<=5 EXCEEDED" in out


def test_wire_budget_fails_on_wire_calls_when_asked(tmp_path, capsys):
    client = _Recorder(_overlay_script())
    code = scenario_cost.main(["--folder", str(tmp_path), "--budget", "8",
                               "--wire-budget", "5", "--poll-ms", "1"], client=client)
    out = capsys.readouterr().out
    assert code == 1
    assert "logical budget: 8/<=8" in out
    assert "wire budget: 10/<=5 EXCEEDED" in out


def test_wire_budget_within_is_exit_0(tmp_path, capsys):
    client = _Recorder(_overlay_script())
    code = scenario_cost.main(["--folder", str(tmp_path), "--budget", "8",
                               "--wire-budget", "10", "--poll-ms", "1"], client=client)
    out = capsys.readouterr().out
    assert code == 0, out
    assert "wire budget: 10/<=10" in out


# -- poll backoff ------------------------------------------------------------


def test_poll_backoff_grows_and_caps():
    assert scenario_cost.grow_poll_ms(100, 1000) == 150
    assert scenario_cost.grow_poll_ms(150, 1000) == 225
    assert scenario_cost.grow_poll_ms(225, 1000) == 338  # ceil, never stalls
    assert scenario_cost.grow_poll_ms(760, 1000) == 1000
    assert scenario_cost.grow_poll_ms(1000, 1000) == 1000
    # A cap below the initial interval cannot shrink it.
    assert scenario_cost.grow_poll_ms(100, 60) == 100


def test_wait_polls_back_off_and_are_clamped_to_the_deadline(tmp_path):
    clock = _Clock()
    script = _overlay_script()
    script["jobs_list"] = [{"jobs": []}]  # the job wait settles at once: only
    script["ui_nav_state"] = [NO_OVERLAY_NAV_STATE]  # the overlay posts sleeps
    client = _Recorder(script)
    report = scenario_cost.ScenarioRunner(
        client, folder=tmp_path, socket_label="fake", wait_timeout_ms=1000,
        poll_ms=100, poll_max_ms=150, sleep=clock.sleep, clock=clock.monotonic,
    ).run()
    step = next(s for s in report.steps if s.name == "wait_for:overlay")
    assert step.status == "blocked"
    # 100 ms initial, then ×1.5 capped at the max: interval growth must not
    # overshoot the deadline, and the last sleep is clamped to what remains.
    sleeps = clock.sleeps
    assert sleeps[0] == 0.1
    assert sleeps[1] == 0.15
    assert all(0 < seconds <= 0.15 for seconds in sleeps)
    assert sum(sleeps) == pytest.approx(1.0, abs=1e-6)
    assert step.wire_calls == len(sleeps) + 1, "one poll per sleep, plus the miss"


# -- overlay predicate: navigation state, never role="canvas" ----------------

def test_overlay_opens_on_a_nav_state_overlay_signal(tmp_path):
    script = _overlay_script()
    script["ui_nav_state"] = [{"sections": [],
                               "overlays": [{"widget": "QuickLookOverlay"}]}]
    client, report = _run(script, tmp_path)
    step = next(s for s in report.steps if s.name == "wait_for:overlay")
    assert step.method == "ui_nav_state"
    assert step.status == "ok"
    assert "signal=nav_state.overlays" in step.detail
    assert client.methods.count("ui_elements") == 1, "the card read, not a canvas"


def test_overlay_opens_on_the_quicklook_navigation_section(tmp_path):
    script = _overlay_script()
    script["ui_nav_state"] = [{"sections": [{"section": "QuickLookNavSection"}],
                               "overlays": []}]
    _client, report = _run(script, tmp_path)
    step = next(s for s in report.steps if s.name == "wait_for:overlay")
    assert step.status == "ok"
    assert "signal=nav_state.sections" in step.detail
    assert "QuickLookNavSection" in step.detail


def test_overlay_is_blocked_only_when_neither_nav_signal_exists(tmp_path):
    client, report = _run(_overlay_script(), tmp_path)  # second reply: both signals
    assert next(s for s in report.steps if s.name == "wait_for:overlay").status == "ok"

    client, report = _run(_overlay_script(), tmp_path, wait_timeout_ms=0)
    step = next(s for s in report.steps if s.name == "wait_for:overlay")
    # First reply has neither signal; a zero budget blocks without touching
    # a canvas role. The step is a normal blocked result, not a crash.
    assert step.status == "blocked"
    assert step.detail.startswith("blocked:overlay timeout")
    assert client.methods.count("ui_elements") == 1


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
