"""Recipe-executor contracts for the fixture-driven live figures.

No display, no app and no capture here: every scenario step is asserted against
a fake control client, because these steps exist to hand *the app* exact params
and a step that quietly dropped one would still photograph something.
The live proof (real Xvfb, real app) stays with the supervisor.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from devtools import help_live, live_fixtures

#: Figures this wave added; each must parse, carry en/dark and a min_size, and
#: land inside a help ``assets`` dir that already exists in the tree.
NEW_FIGURES = (
    "help-image-properties",
    "help-long-press",
    "help-paste-overlay",
    "help-video-editor",
    "help-video-export",
)


class _Recorder:
    """A fake ``LiveClient``: records ``(method, params)`` and can fail on one."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.fail_on = fail_on

    def call(self, method: str, params: dict | None = None) -> dict:
        self.calls.append((method, dict(params or {})))
        if self.fail_on is not None and method == self.fail_on:
            raise help_live.LiveError(f"{method}: injected failure")
        if method == "jobs_list":
            return {"count": 0}
        if method == "list_sessions":
            return {"sessions": [{"session_type": "image_compare", "active": True}]}
        return {}


class _FakeClipboard:
    """Stand-in for ``live_fixtures.ClipboardImage`` (a process owner)."""

    def __init__(self) -> None:
        self.close_calls = 0

    @property
    def closed(self) -> bool:
        return self.close_calls > 0

    def close(self) -> None:
        self.close_calls += 1


def _figure(tmp_path: Path, steps: list[dict], **overrides) -> help_live.LiveFigure:
    entry = {
        "id": "help-probe",
        "capture": "@window",
        "steps": steps,
        "crop": None,
        "destination": "src/resources/help/assets/ui/probe.png",
        "locales": ["en"],
        "themes": ["dark"],
        "min_size": [800, 500],
        "note": "probe",
    }
    entry.update(overrides)
    path = tmp_path / "recipe.json"
    path.write_text(
        json.dumps({"schema_version": 1, "figures": [entry]}), encoding="utf-8"
    )
    return help_live.load_recipes(path)[0]


# --- fixtures ---------------------------------------------------------------


def test_set_clipboard_starts_and_closes_the_fixture(tmp_path, monkeypatch):
    """The clipboard owner is a child process; it must not outlive the figure."""
    started: list[Path] = []
    clip = _FakeClipboard()

    def fake_set_clipboard(path):
        started.append(Path(path))
        return clip

    monkeypatch.setattr(live_fixtures, "set_clipboard_image", fake_set_clipboard)
    figure = _figure(
        tmp_path,
        [{"set_clipboard": "@samples/forest.png"}, {"open_tab": "image_compare"}],
    )
    client = _Recorder()
    help_live.run_steps(client, figure, tmp_path / "samples")

    # ``@samples`` is expanded before the fixture ever sees the path.
    assert started == [tmp_path / "samples" / "forest.png"]
    assert clip.close_calls == 1


def test_a_failing_step_still_closes_the_clipboard(tmp_path, monkeypatch):
    clip = _FakeClipboard()
    monkeypatch.setattr(
        live_fixtures, "set_clipboard_image", lambda _path: clip
    )
    figure = _figure(
        tmp_path,
        [{"set_clipboard": "@samples/forest.png"}, {"action": "image_compare.record"}],
    )
    client = _Recorder(fail_on="run_action")

    with pytest.raises(help_live.LiveError, match="injected failure"):
        help_live.run_steps(client, figure, tmp_path / "samples")

    assert clip.close_calls == 1


def test_caller_scope_keeps_the_clipboard_alive_until_the_capture(
    tmp_path, monkeypatch
):
    """A caller-owned scope spans steps → capture → after_capture."""
    clip = _FakeClipboard()
    monkeypatch.setattr(
        live_fixtures, "set_clipboard_image", lambda _path: clip
    )
    figure = _figure(
        tmp_path,
        [{"set_clipboard": "@samples/forest.png"}, {"sleep": 0}],
    )

    with help_live.FigureFixtures() as fixtures:
        help_live.run_steps(_Recorder(), figure, tmp_path / "samples", fixtures=fixtures)
        # Still owning the selection: the capture has not happened yet.
        assert not clip.closed

    assert clip.close_calls == 1


def test_fixture_close_failures_are_reported_not_swallowed():
    class _Bad:
        def close(self) -> None:
            raise OSError("selection already gone")

    fixtures = help_live.FigureFixtures()
    fixtures.track(_Bad())
    fixtures.close()

    assert fixtures.errors[0].endswith("selection already gone")
    assert "_Bad.close()" in fixtures.errors[0]


# --- post-capture -----------------------------------------------------------


def test_after_capture_releases_the_press_after_the_steps_ran(tmp_path):
    figure = _figure(
        tmp_path,
        [{"ui_press": {"id": "@image_compare.swap", "release": False}}],
        after_capture=[{"ui_press": {"id": "@image_compare.swap", "release": True}}],
    )
    client = _Recorder()

    with help_live.FigureFixtures() as fixtures:
        help_live.run_steps(client, figure, tmp_path, fixtures=fixtures)
        assert client.calls == [
            ("ui_press", {"id": "@image_compare.swap", "release": False})
        ]
        errors = help_live.run_after_capture(client, figure, tmp_path, fixtures)

    assert errors == []
    assert client.calls[-1] == (
        "ui_press",
        {"id": "@image_compare.swap", "release": True},
    )


def test_a_failed_after_capture_step_is_reported_and_the_rest_still_runs(tmp_path):
    """The frame is already captured: a cleanup failure must not discard it."""
    figure = _figure(
        tmp_path,
        [{"sleep": 0}],
        after_capture=[
            {"action": "image_compare.record"},
            {"ui_press": {"id": "@image_compare.swap", "release": True}},
        ],
    )
    client = _Recorder(fail_on="run_action")
    frame = tmp_path / "frame.png"
    frame.write_bytes(b"captured")

    errors = help_live.run_after_capture(
        client, figure, tmp_path, help_live.FigureFixtures()
    )

    assert len(errors) == 1 and errors[0].startswith("run_action")
    assert "injected failure" in errors[0]
    assert frame.read_bytes() == b"captured"
    # The release still ran: one broken step does not abandon the hold.
    assert client.calls[-1] == (
        "ui_press",
        {"id": "@image_compare.swap", "release": True},
    )


def test_after_capture_is_empty_by_default(tmp_path):
    figure = _figure(tmp_path, [{"sleep": 0}])

    assert figure.after_capture == ()
    assert figure.ai_stub is None


# --- step forwarding --------------------------------------------------------


def test_ui_press_and_action_steps_forward_the_control_verb_params(tmp_path):
    figure = _figure(
        tmp_path,
        [
            {"ui_press": {"id": "@image_compare.swap", "release": False, "hold_ms": 250}},
            {"action": "image_compare.video_editor"},
            {"run_action": "image_compare.record"},
            {"open_properties": {"path": "@samples/forest.png"}},
        ],
    )
    client = _Recorder()

    help_live.run_steps(client, figure, tmp_path / "samples")

    assert client.calls == [
        ("ui_press", {"id": "@image_compare.swap", "release": False, "hold_ms": 250}),
        # ``action`` is the recipe spelling of the same control verb.
        ("run_action", {"action_id": "image_compare.video_editor"}),
        ("run_action", {"action_id": "image_compare.record"}),
        ("open_properties", {"path": str(tmp_path / "samples" / "forest.png")}),
    ]


def test_ui_press_release_must_be_a_boolean(tmp_path):
    with pytest.raises(ValueError, match="release"):
        _figure(tmp_path, [{"ui_press": {"id": "x", "release": "no"}}])


def test_ui_press_needs_an_id(tmp_path):
    with pytest.raises(ValueError, match="needs an 'id'"):
        _figure(tmp_path, [{"ui_press": {"release": False}}])


def test_set_clipboard_needs_a_path(tmp_path):
    with pytest.raises(ValueError, match="set_clipboard"):
        _figure(tmp_path, [{"set_clipboard": ""}])


def test_unknown_step_kind_still_fails_loudly(tmp_path):
    with pytest.raises(ValueError, match="unknown step"):
        _figure(tmp_path, [{"wiggle": 1}])


def test_recipe_parses_after_capture_and_ai_stub(tmp_path):
    figure = _figure(
        tmp_path,
        [{"sleep": 0}],
        after_capture=[{"sleep": 0.1}],
        ai_stub={"answer": {"content": "a fixed answer"}},
    )

    assert [step.kind for step in figure.after_capture] == ["sleep"]
    assert figure.ai_stub == {"answer": {"content": "a fixed answer"}}


def test_ai_stub_answer_must_be_an_object_or_string(tmp_path):
    with pytest.raises(ValueError, match="ai_stub"):
        _figure(tmp_path, [{"sleep": 0}], ai_stub={"answer": ["not", "allowed"]})
    with pytest.raises(ValueError, match="ai_stub"):
        _figure(tmp_path, [{"sleep": 0}], ai_stub={})


# --- AI stub seeding --------------------------------------------------------


def test_ai_stub_seeds_the_apps_own_settings_group(tmp_path):
    """The stub must be reachable as the app's *own* endpoint, before boot."""
    stub = live_fixtures.ai_stub_server("a fixed answer")
    try:
        sections = help_live.ai_profile_sections(stub)
        base_url = stub.base_url
        port = stub.port
    finally:
        stub.close()

    assert base_url == f"http://127.0.0.1:{port}/v1"
    group = sections[help_live.AI_SETTINGS_GROUP]
    assert group["base_url"] == base_url
    assert group["enabled"] == "true"
    # ``custom`` is the preset whose endpoint is the user's own; a vendor preset
    # would pin a real URL over the stub's.
    assert group["provider_id"] == "custom"
    assert group["model"] == live_fixtures.STUB_MODEL_ID

    profile = help_live.write_profile(
        tmp_path,
        locale="en",
        theme="dark",
        width=800,
        height=600,
        extra_sections=sections,
    )
    text = profile.read_text(encoding="utf-8")
    assert f"[{help_live.AI_SETTINGS_GROUP}]" in text
    assert f"base_url={base_url}" in text
    # The general section is unchanged by the extra one.
    assert "theme=dark" in text and "export_default_dir=/home/user/Pictures" in text


def test_ai_group_name_is_the_apps_own_constant():
    """A renamed app group would silently leave the stub unused.

    Read from the app's source, not imported: the root suite may not deep-import
    a tab's internals (``tests/contracts/test_root_tests_no_tab_internals_leak``),
    and the constant is a literal, so the AST is the whole truth here.
    """
    source_path = (
        help_live.SRC_ROOT
        / "tabs"
        / "image_gallery"
        / "services"
        / "ai_settings_store.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    groups = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "_QS_GROUP"
        and isinstance(node.value, ast.Constant)
    ]

    assert groups == [help_live.AI_SETTINGS_GROUP]


# --- shipped manifest -------------------------------------------------------


def test_every_new_figure_parses_with_locales_sizes_and_an_asset_dir():
    figures = {figure.id: figure for figure in help_live.load_recipes()}

    for figure_id in NEW_FIGURES:
        assert figure_id in figures, f"{figure_id} missing from the recipe file"
        figure = figures[figure_id]
        assert figure.locales == ("en",)
        assert figure.themes == ("dark",)
        assert figure.min_size is not None, f"{figure_id} needs a min_size"
        assert figure.note, f"{figure_id} needs a note"
        assert "/resources/help/assets/" in figure.destination
        where = help_live.REPO_ROOT / figure.destination
        assert where.parent.is_dir(), f"{figure_id} destination dir does not exist"


def test_held_press_figure_releases_in_after_capture():
    figures = {figure.id: figure for figure in help_live.load_recipes()}
    figure = figures["help-long-press"]

    held = [step for step in figure.steps if step.kind == "ui_press"]
    assert held and held[-1].kwargs["release"] is False
    released = [step for step in figure.after_capture if step.kind == "ui_press"]
    assert released and released[-1].kwargs["release"] is True
    assert released[-1].kwargs["id"] == held[-1].kwargs["id"]


def test_clipboard_figure_pastes_through_the_platform_action():
    """A clipboard step and a paste trigger must both be present, in order."""
    figure = {f.id: f for f in help_live.load_recipes()}["help-paste-overlay"]
    kinds = [step.kind for step in figure.steps]

    assert "set_clipboard" in kinds
    assert kinds.index("set_clipboard") < kinds.index("run_action")
    paste = figure.steps[kinds.index("run_action")]
    assert paste.kwargs["action_id"] == "platform.paste_clipboard_image"
    assert figure.capture == "@window"


def test_list_prints_the_new_figures(capsys):
    assert help_live.main(["--list"]) == 0
    printed = capsys.readouterr().out

    for figure_id in NEW_FIGURES:
        assert figure_id in printed
    assert "locales=en themes=dark" in printed


def test_module_imports_without_a_display():
    """Import must stay side-effect free (no QApplication, no X connection)."""
    env = {key: value for key, value in os.environ.items() if key != "DISPLAY"}
    env["PYTHONPATH"] = str(help_live.SRC_ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import devtools.help_live as m; print(m.AI_SETTINGS_GROUP)",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(help_live.REPO_ROOT),
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == help_live.AI_SETTINGS_GROUP
