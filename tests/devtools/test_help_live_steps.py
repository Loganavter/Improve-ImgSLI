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

from devtools import help_figures, help_live, live_fixtures

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


# --- crop selectors ---------------------------------------------------------


class _CropClient:
    """Answers the two read-only verbs a crop is derived from, and nothing else."""

    def __init__(
        self, *, directory: Path, elements=None, windows=None, overlays=None, active=""
    ):
        self.directory = Path(directory)
        self.elements = list(elements or [])
        self.windows = list(windows or [])
        self.overlays = list(overlays or [])
        self.active = active
        self.calls: list[tuple[str, dict]] = []

    def call(self, method, params=None):
        self.calls.append((method, dict(params or {})))
        if method == "ui_elements":
            return {
                "count": len(self.elements),
                "total": len(self.elements),
                "elements": self.elements,
            }
        if method == "dump_ui_layout":
            path = self.directory / "ui-layout.json"
            path.write_text(
                json.dumps(
                    {
                        "windows": self.windows,
                        "overlays": self.overlays,
                        "active_window": self.active,
                    }
                ),
                encoding="utf-8",
            )
            return {"path": str(path), "windows": len(self.windows)}
        raise AssertionError(f"unexpected control call: {method}")


def _row(element_id, rect, *, action_id=None, visible=True):
    return {
        "id": element_id,
        "action_id": action_id,
        "role": "button",
        "label": element_id,
        "rect": list(rect),
        "screen_rect": list(rect),
        "visible": visible,
    }


def _window(class_name, geometry, *, active=False, visible=True, object_name=""):
    node = {
        "class": class_name,
        "object_name": object_name,
        "geometry": list(geometry),
        "visible": visible,
    }
    if active:
        node["is_active_window"] = True
    return node


def _overlay(class_name, screen_rect, *, visible=True, object_name="", targets=None):
    """One ``overlays`` row of the layout dump (a child overlay, screen space).

    Unlike a ``windows`` row this carries ``screen_rect`` directly: the node's
    ``geometry`` is parent-local, and the crop is in screen pixels.
    """
    node = {
        "class": class_name,
        "object_name": object_name,
        "parent_class": "MainWindow",
        "visible": visible,
        "screen_rect": list(screen_rect),
    }
    if targets:
        node["targets"] = [
            {"name": name, "screen_rect": list(rect)} for name, rect in targets.items()
        ]
    return node


def test_crop_by_ids_is_the_union_of_the_controls(tmp_path):
    """Two adjacent controls crop as one region (the two long-press buttons)."""
    client = _CropClient(
        directory=tmp_path,
        elements=[
            _row("MainWindow/0.1@image_compare.clear_list1", (500, 100, 36, 36),
                 action_id="image_compare.clear_list1"),
            _row("MainWindow/0.2@image_compare.swap", (544, 100, 36, 36),
                 action_id="image_compare.swap"),
        ],
    )

    crop = help_live._element_crop(
        client,
        {"ids": ["@image_compare.clear_list1", "@image_compare.swap"], "pad": 4},
    )

    # 500..580 wide (36 + 8 layout spacing + 36), 100..136 high, pad not applied here.
    assert crop == (4, 500, 100, 80, 36)
    # A disabled-but-present control still has to be addressable.
    assert client.calls[0] == ("ui_elements", {"include_disabled": True})


def test_crop_by_ids_refuses_a_control_that_is_not_on_screen(tmp_path):
    client = _CropClient(
        directory=tmp_path,
        elements=[_row("MainWindow/0.1@image_compare.swap", (1, 2, 36, 36), visible=False)],
    )

    with pytest.raises(help_live.LiveError, match="not visible"):
        help_live._element_crop(client, {"ids": ["@image_compare.swap"]})


def test_crop_by_ids_names_the_missing_reference(tmp_path):
    client = _CropClient(directory=tmp_path, elements=[])

    with pytest.raises(help_live.LiveError, match="@image_compare.swap"):
        help_live._element_crop(client, {"ids": ["@image_compare.swap"]})


def test_crop_by_window_uses_the_dumped_geometry(tmp_path):
    """A dialog has no element row; its own top-level rect is the crop."""
    client = _CropClient(
        directory=tmp_path,
        windows=[_window("VideoEditorDialog", (100, 40, 1200, 850))],
    )

    assert help_live._element_crop(client, {"window": "VideoEditorDialog", "pad": 0}) == (
        0,
        100,
        40,
        1200,
        850,
    )


def test_crop_by_window_prefers_the_active_instance(tmp_path):
    client = _CropClient(
        directory=tmp_path,
        windows=[
            _window("SettingsDialog", (0, 0, 800, 600)),
            _window("SettingsDialog", (300, 200, 800, 600), active=True),
        ],
    )

    assert help_live._element_crop(client, {"window": "SettingsDialog", "pad": 0})[1:3] == (
        300,
        200,
    )


def test_crop_by_window_fails_when_the_surface_is_not_on_screen(tmp_path):
    """A missing overlay must fail the figure, never crop empty background."""
    client = _CropClient(
        directory=tmp_path,
        windows=[_window("MainWindow", (0, 0, 1296, 816), active=True)],
        active="MainWindow:",
    )

    with pytest.raises(help_live.LiveError, match="PasteDirectionOverlay"):
        help_live._element_crop(client, {"window": "PasteDirectionOverlay", "pad": 0})


def test_a_hidden_window_is_not_a_crop_target(tmp_path):
    client = _CropClient(
        directory=tmp_path,
        windows=[_window("PasteDirectionOverlay", (0, 0, 1280, 800), visible=False)],
    )

    with pytest.raises(help_live.LiveError, match="no visible window"):
        help_live._element_crop(client, {"window": "PasteDirectionOverlay", "pad": 0})


def test_crop_by_overlay_uses_the_overlay_rect_when_it_paints_nothing(tmp_path):
    """An in-window overlay is a child of its window, so it is not in ``windows``.

    RED-BEFORE: the only selectors were ``id``/``ids``, ``window`` and
    ``role``+``label``; the picker has no element row and no top-level window,
    so every capture of ``help-paste-overlay`` failed with "no visible window".
    """
    client = _CropClient(
        directory=tmp_path,
        windows=[_window("MainWindow", (0, 0, 1280, 800), active=True)],
        overlays=[_overlay("PasteDirectionOverlay", (160, 200, 320, 120))],
    )

    assert help_live._element_crop(
        client, {"overlay": "PasteDirectionOverlay", "pad": 0}
    ) == (0, 160, 200, 320, 120)


def test_crop_by_overlay_crops_the_union_of_its_painted_targets(tmp_path):
    """The picker paints its targets; they own no widget and no element row.

    The overlay's own rect is the whole parent window (it fills it), so a crop
    of *that* would frame the loaded session instead of the picker. The painted
    target rects are the honest frame.
    """
    client = _CropClient(
        directory=tmp_path,
        overlays=[
            _overlay(
                "PasteDirectionOverlay",
                (0, 0, 1280, 800),
                targets={
                    "left": (440, 340, 120, 120),
                    "right": (760, 340, 120, 120),
                    "cancel": (610, 370, 60, 60),
                },
            )
        ],
    )

    # 440..880 wide, 340..460 high; the pad is returned, not applied here.
    assert help_live._element_crop(
        client, {"overlay": "PasteDirectionOverlay", "pad": 8}
    ) == (8, 440, 340, 440, 120)


def test_crop_by_overlay_full_opts_out_of_the_painted_union(tmp_path):
    """A documented fallback: the whole overlay (i.e. the whole parent window)."""
    client = _CropClient(
        directory=tmp_path,
        overlays=[
            _overlay(
                "PasteDirectionOverlay",
                (12, 7, 1280, 800),
                targets={"left": (440, 340, 120, 120)},
            )
        ],
    )

    assert help_live._element_crop(
        client, {"overlay": "PasteDirectionOverlay", "pad": 0, "full": True}
    ) == (0, 12, 7, 1280, 800)


def test_crop_by_overlay_names_the_overlays_that_are_on_screen(tmp_path):
    """A missing overlay must say which overlays *are* there — typo vs dismissed."""
    client = _CropClient(
        directory=tmp_path,
        overlays=[_overlay("QuickLookOverlay", (0, 0, 800, 600))],
    )

    with pytest.raises(help_live.LiveError, match="QuickLookOverlay"):
        help_live._element_crop(client, {"overlay": "PasteDirectionOverlay"})


def test_crop_by_overlay_refuses_a_dismissed_overlay(tmp_path):
    client = _CropClient(
        directory=tmp_path,
        overlays=[_overlay("PasteDirectionOverlay", (0, 0, 1280, 800), visible=False)],
    )

    with pytest.raises(help_live.LiveError, match="not visible"):
        help_live._element_crop(client, {"overlay": "PasteDirectionOverlay"})


# --- the dump section the overlay selector reads ----------------------------


def test_the_dump_lists_in_window_overlays_with_screen_rects(qapp):
    """``windows`` can never carry an in-window overlay: it is a child widget.

    The paste picker fills its parent window, so its own ``geometry`` (parent
    -local) and screen rect are the *window*; only the painted target rects say
    where the picker actually is. This pins the dump section that the
    ``overlay`` crop selector resolves against.
    """
    from types import SimpleNamespace

    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QWidget
    from sli_ui_toolkit.ui.widgets.overlays.in_window_overlay import (
        TopLevelInWindowOverlay,
    )

    from devtools.ui_layout_dump import dump_all_windows

    host = QWidget()
    host.setObjectName("HostWindow")
    host.setGeometry(100, 120, 640, 480)
    overlay = TopLevelInWindowOverlay(host, close_on_deactivate=False)
    overlay.setObjectName("ProbeOverlay")
    # The read-only protocol: overlay-local rects, by name. A real overlay that
    # paints its targets (the paste picker) implements the same attribute.
    overlay.painted_target_rects = lambda: {"left": QRect(10, 20, 30, 40)}
    host.show()
    overlay.show_overlay()
    qapp.processEvents()
    try:
        dump = dump_all_windows(SimpleNamespace(all_actions=lambda: []))
    finally:
        host.close()
        host.deleteLater()

    assert [w for w in dump["windows"] if w["class"] == "TopLevelInWindowOverlay"] == [], (
        "an in-window overlay is a child, so it must never be reported as a window"
    )
    rows = [row for row in dump["overlays"] if row.get("object_name") == "ProbeOverlay"]
    assert len(rows) == 1, dump["overlays"]
    row = rows[0]
    assert row["class"] == "TopLevelInWindowOverlay"
    assert row["parent_class"] == "QWidget"
    assert row["visible"] is True
    # Both rects are screen space (mapToGlobal), not parent-local geometry.
    origin = overlay.mapToGlobal(overlay.rect().topLeft())
    assert row["screen_rect"] == [
        origin.x(),
        origin.y(),
        overlay.width(),
        overlay.height(),
    ]
    assert row["targets"] == [
        {
            "name": "left",
            "screen_rect": [origin.x() + 10, origin.y() + 20, 30, 40],
        }
    ]


# --- capture origin (screen_rect → image pixels) -----------------------------


def test_the_root_grab_is_one_to_one_with_the_screen(tmp_path):
    assert help_live._capture_origin(
        _CropClient(directory=tmp_path), "@screen", (1400, 1000)
    ) == (0, 0)


def test_a_window_grab_starts_at_that_windows_screen_position(tmp_path):
    """No centred-shadow guess: the dump names where the grabbed window sits."""
    client = _CropClient(
        directory=tmp_path,
        windows=[_window("MainWindow", (12, 7, 1296, 816), active=True)],
        active="MainWindow:",
    )

    assert help_live._capture_origin(client, "@window", (1296, 816)) == (12, 7)


def test_a_clipped_or_scaled_grab_has_no_known_origin(tmp_path):
    client = _CropClient(
        directory=tmp_path,
        windows=[_window("MainWindow", (0, 0, 1296, 816), active=True)],
        active="MainWindow:",
    )

    with pytest.raises(help_live.LiveError, match="clipped"):
        help_live._capture_origin(client, "@window", (1296, 400))


def test_an_unlisted_active_window_fails_loudly(tmp_path):
    client = _CropClient(directory=tmp_path, windows=[], active="MainWindow:")

    with pytest.raises(help_live.LiveError, match="not in the layout dump"):
        help_live._capture_origin(client, "@window", (1296, 816))


def test_crop_is_clamped_to_the_capture_instead_of_padded(tmp_path):
    """PIL pads an out-of-bounds crop with black, which reads as a defect."""
    from PIL import Image

    shot = tmp_path / "shot.png"
    Image.new("RGB", (200, 100), (10, 20, 30)).save(shot)
    out = tmp_path / "x.png"

    help_live.crop_and_install(shot, out, (180, 80, 60, 40))

    with Image.open(out) as image:
        assert image.size == (20, 20)


def test_a_crop_outside_the_capture_is_an_error(tmp_path):
    from PIL import Image

    shot = tmp_path / "shot.png"
    Image.new("RGB", (200, 100), (10, 20, 30)).save(shot)

    with pytest.raises(help_live.LiveError, match="outside the 200x100"):
        help_live.crop_and_install(shot, tmp_path / "x.png", (400, 400, 50, 50))


# --- shipped manifest -------------------------------------------------------


def test_every_new_figure_parses_with_locales_sizes_and_an_asset_dir():
    figures = {figure.id: figure for figure in help_live.load_recipes()}

    for figure_id in NEW_FIGURES:
        assert figure_id in figures, f"{figure_id} missing from the recipe file"
        figure = figures[figure_id]
        # A figure's matrix is declared per locale x theme (the variant wave
        # installs cells), so the stable contract is membership, not one cell.
        assert figure.locales and set(figure.locales) <= set(help_figures.LOCALES)
        assert figure.themes and set(figure.themes) <= set(help_figures.THEMES)
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


def test_held_press_figure_crops_by_the_reference_it_pressed():
    """The crop must name the pressed control, not a caption that matches it.

    A ``role``+``label`` crop is a substring scan over every window (it pointed
    at "Swap Images" wherever that caption landed); the reference form is the
    same ``@action`` id the press drives, so the two can never diverge.
    """
    figure = {f.id: f for f in help_live.load_recipes()}["help-long-press"]
    pressed = [step for step in figure.steps if step.kind == "ui_press"][-1]
    spec = figure.crop_element or {}

    assert "ids" in spec, "the long-press crop must use inventory references"
    assert pressed.kwargs["id"] in spec["ids"]
    assert spec.get("pad", 0) > 0, "the pressed control needs its margin in frame"
    # Screen-coordinate crop ⇒ the 1:1 root grab (a window grab's origin is a
    # separate question, and the +8 guess it used once clipped the button).
    assert figure.capture == "@screen"


def test_window_and_overlay_figures_crop_to_their_own_surface():
    """A dialog is a top-level window; a picker is an in-window child overlay."""
    figures = {f.id: f for f in help_live.load_recipes()}

    dialog = figures["help-video-export"]
    assert dialog.capture == "@screen", (
        "@window grabs app.activeWindow(), which stays the main window while the "
        "editor is open"
    )
    assert (dialog.crop_element or {}).get("window") == "VideoEditorDialog"

    picker = figures["help-paste-overlay"]
    assert picker.capture == "@screen"
    # RED-BEFORE: `window` names only ``topLevelWidgets()``, so the picker (a
    # child of the window it fills) could never resolve — all 8 captures of the
    # figure failed with "no visible window 'PasteDirectionOverlay'".
    spec = picker.crop_element or {}
    assert spec.get("overlay") == "PasteDirectionOverlay"
    assert "window" not in spec, "an in-window overlay is not a top-level window"


def test_clipboard_figure_pastes_through_the_platform_action():
    """A clipboard step and a paste trigger must both be present, in order."""
    figure = {f.id: f for f in help_live.load_recipes()}["help-paste-overlay"]
    kinds = [step.kind for step in figure.steps]

    assert "set_clipboard" in kinds
    assert kinds.index("set_clipboard") < kinds.index("run_action")
    paste = figure.steps[kinds.index("run_action")]
    assert paste.kwargs["action_id"] == "platform.paste_clipboard_image"
    # The picker is a window-level overlay a window grab never includes (and its
    # only other content is the loaded session), so the frame is the X root.
    assert figure.capture == "@screen"


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
