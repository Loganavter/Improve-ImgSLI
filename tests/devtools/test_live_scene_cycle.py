"""S3 — the full canvas scene cycle (``devtools/live_scene_cycle``).

The cycle under test walks *build -> verify -> capture -> record -> export* and
decides every hop from something the app exposes: the S1 scene JSON, the log
ring, or an artifact on disk. No hop is decided by a sleep.

What is real here and what is a stand-in, stated up front (the whole point of
the tool is that this distinction is never blurred):

* **real** — the scene read (``get_canvas_scene``), the scene commands
  (``set_scene_commands``), the serialization and the log/artifact *rules* run on
  a real ``CanvasWidget`` / ``Store`` through the real ``ControlHandlers``;
* **stand-in** — the app transport and the recording/encode chain. A clone
  cannot boot the app (the venv is gitignored) and offscreen Qt paints the
  toolkit pipeline black, so the test app models exactly the signals the real
  app emits: the recorder's frame trace line (``recorder.py:47-53``), the video
  editor's Find Actions appearing after finalize (``recording_flow.py:190``),
  the encoder's ``Rendering N frames`` / ``Video export successful: <path>``
  lines (``video_export/service.py:921,961``) and the artifact itself. The
  supervisor runs the live proof on a real display; see ``DONE.md``.

Falsification (proven RED on the pre-change tree): ``live_scene_cycle.py`` and
this file do not exist there and nothing imports a scene cycle, so every test
fails at collection/import — none of them restates code that was already
present. The negative cases (byte drift detected, timeout surfaces the last
state, a missing loupe fails by name) exist so the tests cannot pass by
asserting whatever the tool happened to do.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from core.control.handlers import ControlHandlers
from core.store import Store
from devtools import live_scene_cycle as cycle_mod
from devtools.live_scene_cycle import SceneCycle, main
from devtools.scenario_cost import ControlError
from PySide6.QtWidgets import QApplication, QWidget
from ui.actions.registry import ActionRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
EDITOR_GROUP_ACTION = "image_compare.video_editor.group.video.export_actions"
EDITOR_EXPORT_ACTION = f"{EDITOR_GROUP_ACTION}.image_compare.action.export_video"


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# a real Image Compare canvas (same construction the S1/S2 tests use)
# ---------------------------------------------------------------------------


def _ic_page(qapp, *, loupes: int = 1):
    """A real Image Compare canvas + store; the first loupe starts hidden.

    Hidden on purpose: the cycle must then *command* it visible, so the build hop
    covers ``magnifier.set_visible`` instead of skipping it as already satisfied.
    """
    from domain.types import Rect
    from tabs.image_compare.canvas.features.magnifier.geometry.layout_plan import (
        build_magnifier_layout,
    )
    from tabs.image_compare.canvas.features.magnifier.scene.build import (
        build_magnifier_objects,
    )
    from tabs.image_compare.canvas.features.magnifier.state.store import (
        add_magnifier_model,
        set_active_magnifier_id,
        update_magnifier_model,
    )
    from tabs.image_compare.canvas.scene import build_render_scene
    from tabs.image_compare.canvas.widget import CanvasWidget
    from tabs.image_compare.tab import ImageCompareTab
    from ui.canvas_infra.scene.context import CanvasSceneBuildContext
    from ui.canvas_infra.scene.models import CanvasSceneGraph
    from ui.canvas_presentation.plan import CanvasRenderPlan

    ImageCompareTab().register_canvas_features()

    store = Store()
    viewport = store.viewport
    viewport.geometry_state.pixmap_width = 640
    viewport.geometry_state.pixmap_height = 400
    view_state = viewport.view_state

    if loupes:
        add_magnifier_model(view_state, viewport.render_config, "loupe-a")
        update_magnifier_model(view_state, viewport.render_config, "loupe-a", visible=False)
        set_active_magnifier_id(view_state, "loupe-a")

    canvas = CanvasWidget()
    canvas.resize(800, 600)
    canvas.runtime_state._store = store

    context = CanvasSceneBuildContext(
        store=store,
        image_label=canvas,
        bounds=Rect(0, 0, 640, 400),
        label_width=800,
        label_height=600,
        pix_w=640,
        pix_h=400,
    )
    canvas.runtime_state._canvas_scene_graph = CanvasSceneGraph(
        bounds=Rect(0, 0, 640, 400),
        objects=tuple(build_magnifier_objects(context)),
        active_object_id="loupe-a",
    )
    canvas._active_render_plan = CanvasRenderPlan(
        image1=None,
        image2=None,
        source_image1=None,
        source_image2=None,
        source_key=(),
        canvas_w=640,
        canvas_h=400,
        render_scene=build_render_scene(store, apply_channel_mode_in_shader=True),
        overlay_layout=build_magnifier_layout(
            viewport,
            width=640,
            height=400,
            canvas_width=640,
            canvas_height=400,
            divider_thickness_px=3,
        ),
        capture_visible=False,
        capture_color=None,
        guides_enabled=False,
        guides_color=None,
        guides_thickness=0,
    )

    page = QWidget()
    canvas.setParent(page)
    return SimpleNamespace(store=store, canvas=canvas, page=page, view_state=view_state)


def _handlers(tmp_path, *, page) -> ControlHandlers:
    """``ControlHandlers`` over that page (the read verb's discovery pinned)."""

    class _Contract:
        def get_canvas_geometry_provider(self):
            return SimpleNamespace()

    handlers = ControlHandlers(
        window=SimpleNamespace(store=None),
        app=None,
        artifacts_dir=tmp_path / "artifacts",
        registry_provider=lambda: ActionRegistry(),
    )
    handlers._tabs = lambda: [("image_compare", _Contract())]  # type: ignore[assignment]
    from core.control import scene_read

    scene_read.page_widget = lambda _handlers, _kind: page  # type: ignore[assignment]
    return handlers


# ---------------------------------------------------------------------------
# the app stand-in: real scene paths + the app's own record/encode signals
# ---------------------------------------------------------------------------


class FakeClock:
    """Deterministic time for the cycle's deadline arithmetic (no real waiting)."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(float(seconds), 1e-3)


class _FakeApp:
    """A live app stand-in with the real scene paths and the real encode signals."""

    def __init__(
        self,
        *,
        handlers: ControlHandlers,
        store: Store,
        out_dir: Path,
        editor_polls: int = 2,
        export_polls: int = 3,
        emit_recording_trace: bool = True,
        fail_export: bool = False,
        render_variant: int = 0,
        rhi_layers: int = 1,
        frames: int = 42,
        magnifier_toggle_creates: bool = True,
    ) -> None:
        self.handlers = handlers
        self.store = store
        self.out_dir = Path(out_dir)
        self.editor_polls = editor_polls
        self.export_polls = export_polls
        self.emit_recording_trace = emit_recording_trace
        self.fail_export = fail_export
        self.render_variant = render_variant
        self.rhi_layers = rhi_layers
        self.frames = frames
        self.magnifier_toggle_creates = magnifier_toggle_creates
        self.log: list[tuple[str, str]] = []
        self.recording = False
        self.recording_data = False
        self.pending_editor = False
        self.finalize_ticks = 0
        self.editor_open = False
        self.export_pending = False
        self.export_ticks = 0
        self.video_path: Path | None = None
        self.captures = 0
        self.calls: list[str] = []
        self.clock = FakeClock()

    # -- the wire ----------------------------------------------------------

    def call(self, method: str, params: dict | None = None) -> dict:
        params = params or {}
        self.calls.append(method)
        if method == "ping":
            return {"pong": True}
        if method == "read_log":
            return self._read_log(params)
        if method == "list_actions":
            return self._list_actions(params)
        if method == "run_action":
            return self._run_action(params)
        if method == "open_tab":
            return {"tab": params.get("tab"), "via": "action", "reused": True}
        if method == "open_folder":
            return self._open_folder(params)
        if method == "capture_live":
            return self._capture()
        if method in {"get_canvas_scene", "set_scene_commands"}:
            try:
                return self.handlers.handle(method, params)
            except Exception as exc:  # the app's own refusal shape
                raise ControlError(str(exc), getattr(exc, "hint", None)) from None
        raise ControlError(f"the fake app does not implement {method!r}", None)

    def close(self) -> None:
        return None

    # -- log ring ----------------------------------------------------------

    def _log_line(self, text: str, level: str = "INFO") -> None:
        self.log.append((level, text))

    def _read_log(self, params: dict) -> dict:
        self._advance()
        threshold = params.get("level")
        rows = [
            {"n": index + 1, "level": level, "text": text}
            for index, (level, text) in enumerate(self.log)
        ]
        if threshold:
            order = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            floor = order.index(threshold) if threshold in order else 0
            rows = [row for row in rows if order.index(row["level"]) >= floor]
        count = int(params.get("n", 200) or 0)
        tail = rows[-count:] if count else rows
        return {"total_lines": len(self.log), "returned": len(tail), "lines": tail}

    # -- actions -----------------------------------------------------------

    def _list_actions(self, params: dict) -> dict:
        self._advance()
        result = self.handlers.handle("list_actions", params)
        rows = list(result.get("actions") or [])
        needle = str(params.get("query") or "").lower()
        if self.editor_open:
            for action_id in (EDITOR_GROUP_ACTION, EDITOR_EXPORT_ACTION):
                if needle and needle not in action_id.lower():
                    continue
                rows.append(
                    {
                        "action_id": action_id,
                        "label": action_id,
                        "owner_tab": "image_compare",
                        "topic": "video",
                        "shortcut": None,
                        "enabled": True,
                        "reason": None,
                    }
                )
        return {"count": len(rows), "actions": rows}

    def _run_action(self, params: dict) -> dict:
        action_id = str(params.get("action_id") or "")
        if action_id == cycle_mod.RECORD_ACTION:
            self.recording = True
            self.recording_data = True
            if self.emit_recording_trace:
                self._log_line(
                    "[video-editor-debug] capture_frame ENTER is_recording=True "
                    "elapsed=0.000 force=False timeline_len_before=0",
                    "WARNING",
                )
            return {"ran": True, "action_id": action_id}
        if action_id == cycle_mod.VIDEO_EDITOR_ACTION:
            if self.recording:
                # ``recording_flow.open_video_editor``: park the open and stop.
                self.recording = False
                self.pending_editor = True
                self.finalize_ticks = self.editor_polls
            elif not self.recording_data:
                self._log_line("No recording available to edit.", "WARNING")
            else:
                self.editor_open = True
            return {"ran": True, "action_id": action_id}
        if action_id == EDITOR_EXPORT_ACTION:
            if not self.editor_open:
                raise ControlError("the video editor is not open", None)
            self.export_pending = True
            self.export_ticks = self.export_polls
            self.video_path = self.out_dir / "video" / "cycle.mp4"
            self.video_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_line(
                f"Rendering {self.frames} frames to {self.video_path} using FFmpeg..."
            )
            return {"ran": True, "action_id": action_id}
        if action_id == cycle_mod.MAGNIFIER_ENABLED_ACTION:
            if self.magnifier_toggle_creates:
                from tabs.image_compare.canvas.features.magnifier.state.store import (
                    add_magnifier_model,
                )

                viewport = self.store.viewport
                add_magnifier_model(viewport.view_state, viewport.render_config, "loupe-a")
            return {"ran": True, "action_id": action_id}
        # Everything else is the real registry (the fake app has no others).
        return self.handlers.handle("run_action", params)

    def _open_folder(self, params: dict) -> dict:
        """Load one staged image into the named slot (the app's own document)."""
        from tabs.image_compare.state.document import DocumentModel, ImageItem

        slot = int(params.get("slot") or 1)
        folder = Path(str(params.get("path")))
        images = sorted(
            path for path in folder.iterdir()
            if path.is_file() or path.is_symlink()
        )
        assert len(images) == 1, f"staging must hold exactly one image, got {images}"
        document = self.store.get_session_state_slot("document") or DocumentModel()
        item = ImageItem(path=str(images[0]), display_name=images[0].name)
        if slot == 1:
            document.image_list1 = [item]
            document.current_index1 = 0
        else:
            document.image_list2 = [item]
            document.current_index2 = 0
        self.store.set_session_state_slot("document", document)
        return {"routed": True, "path": str(folder), "tab": "image_compare", "images": 1}

    # -- capture / encode --------------------------------------------------

    def _capture(self) -> dict:
        """Render the scene into a PNG (a deterministic function of the scene)."""
        scene = self.handlers.handle("get_canvas_scene", {"tab": "image_compare"})
        self.captures += 1
        directory = self.out_dir / "captures"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"live-capture-{self.captures}.png"
        canvas = scene.get("canvas") or {"w": 320, "h": 200}
        image = QImage(320, 200, QImage.Format.Format_RGB32)
        image.fill(QColor(18 + self.render_variant, 24, 32))
        magnifiers = scene.get("magnifiers") or []
        model = (magnifiers[0].get("model") or {}) if magnifiers else {}
        position = model.get("position_relative") or [0.5, 0.5]
        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(200, 120, 40))
            painter.drawEllipse(
                QPointF(float(position[0]) * 320.0, float(position[1]) * 200.0),
                24.0,
                24.0,
            )
            painter.setBrush(QColor(60, 200, 140))
            painter.drawRect(4, 4, int(canvas.get("w") or 0) % 64 + 8, 10)
        finally:
            painter.end()
        assert image.save(str(target), "PNG")
        return {
            "path": str(target),
            "what": "image_compare",
            "method": "widget",
            "size": [image.width(), image.height()],
            "rhi_layers": self.rhi_layers,
        }

    # -- the model's progress ----------------------------------------------

    def _advance(self) -> None:
        """One poll interval of app progress (a real app runs on wall time)."""
        if self.pending_editor:
            self.finalize_ticks -= 1
            if self.finalize_ticks <= 0:
                self.pending_editor = False
                self.editor_open = True
                self._log_line("on_recording_finalized pending=True")
        if self.export_pending:
            self.export_ticks -= 1
            if self.export_ticks <= 0:
                self.export_pending = False
                if self.fail_export:
                    self._log_line("FFmpeg exited with error code 1", "ERROR")
                else:
                    assert self.video_path is not None
                    self.video_path.write_bytes(b"fake-mp4-payload" * 32)
                    self._log_line(f"Video export successful: {self.video_path}")
                    self._log_line(f"Video export finished: {self.video_path}")


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_and_inputs(qapp, tmp_path):
    """A fake app + two real image files on disk."""
    from PIL import Image

    images = tmp_path / "source"
    images.mkdir()
    created = []
    for name, color in (("left.png", (200, 30, 30)), ("right.png", (30, 30, 200))):
        path = images / name
        Image.new("RGB", (64, 48), color).save(path)
        created.append(path)
    page = _ic_page(qapp)
    handlers = _handlers(tmp_path, page=page.page)
    app = _FakeApp(handlers=handlers, store=page.store, out_dir=tmp_path / "cycle")
    return SimpleNamespace(app=app, left=created[0], right=created[1], tmp_path=tmp_path)


def _run(app, inputs, *, out_name="cycle", **kwargs):
    out_dir = inputs.tmp_path / out_name
    cycle = SceneCycle(
        channel=app,
        out_dir=out_dir,
        clock=app.clock,
        sleep=app.clock.sleep,
        **kwargs,
    )
    report = cycle.run(inputs.left, inputs.right)
    return report, out_dir


def _steps(report) -> dict[str, dict]:
    return {row["step"]: row for row in report["steps"]}


# ---------------------------------------------------------------------------
# (a) every observable hop is asserted against its signal
# ---------------------------------------------------------------------------


def test_cycle_observes_every_hop_and_writes_the_scene_the_app_reports(app_and_inputs):
    report, out_dir = _run(app_and_inputs.app, app_and_inputs)

    assert report["ok"] is True, json.dumps(report["failures"], indent=2)
    steps = _steps(report)
    for name in (
        "open_tab",
        "load_pair",
        "build_scene",
        "verify_scene",
        "capture_png",
        "record_start",
        "scene_while_recording",
        "stop_and_open_editor",
        "export_video",
    ):
        assert steps[name]["status"] == "observed", (name, steps[name])
        assert steps[name]["observable"], f"{name} must name its signal"

    # The scene JSON on disk is the app's own read, serialized canonically, and
    # it holds the state the cycle promised (not merely "the commands returned").
    scene_file = out_dir / "scene.json"
    assert scene_file.is_file()
    scene = json.loads(scene_file.read_text(encoding="utf-8"))
    assert scene == report["scene"]
    assert report["scene_json"]["sha256"] == cycle_mod.sha256_text(
        scene_file.read_text(encoding="utf-8")
    )
    assert scene["scene_source"] == "ic_scene"
    loupe = scene["magnifiers"][0]
    assert loupe["visible"] is True, "the cycle had to command the hidden loupe visible"
    assert loupe["model"]["size_relative"] == pytest.approx(cycle_mod.LOUPE_SIZE)
    assert loupe["model"]["position_relative"] in [
        list(cycle_mod.LOUPE_POSITION_A),
        list(cycle_mod.LOUPE_POSITION_B),
    ]
    assert scene["dividers"][0]["thickness"] == pytest.approx(cycle_mod.DIVIDER_THICKNESS)
    # The pair really is the pair the cycle staged (S1 read, slot by slot).
    assert [pane["slot"] for pane in scene["panes"]] == [1, 2]
    assert {Path(pane["path"]).name for pane in scene["panes"]} == {"left.png", "right.png"}

    # Artifacts: present, non-empty, and their hashes are the report's.
    png = Path(report["artifacts"]["png"]["path"])
    video = Path(report["artifacts"]["video"]["path"])
    assert png.is_file() and png.stat().st_size > 0
    assert report["artifacts"]["png"]["bytes"] == png.stat().st_size
    assert report["artifacts"]["png"]["rhi_layers"] == 1
    assert video.is_file() and video.stat().st_size > 0
    assert report["artifacts"]["video"]["frames_reported"] == app_and_inputs.app.frames

    # The hop with no observable is NAMED, and it is not one that was observed.
    named = {row["step"] for row in report["unobservable"]}
    assert "video_export_job" in named
    assert "record_start" not in named, "the frame trace was present, so it was observed"
    assert "jobs.py" in next(
        row["reason"] for row in report["unobservable"] if row["step"] == "video_export_job"
    )


def test_recording_start_without_the_debug_trace_is_reported_unobservable(qapp, tmp_path):
    """No trace in the log ring: the hop must say so, not claim it was seen."""
    from PIL import Image

    images = tmp_path / "source"
    images.mkdir()
    left = images / "left.png"
    Image.new("RGB", (64, 48), (10, 10, 10)).save(left)
    page = _ic_page(qapp)
    app = _FakeApp(
        handlers=_handlers(tmp_path, page=page.page),
        store=page.store,
        out_dir=tmp_path / "cycle",
        emit_recording_trace=False,
    )
    cycle = SceneCycle(
        channel=app, out_dir=tmp_path / "cycle", clock=app.clock, sleep=app.clock.sleep
    )
    report = cycle.run(left, left)

    steps = _steps(report)
    assert steps["record_start"]["status"] == "unobservable"
    named = {row["step"]: row for row in report["unobservable"]}
    assert "record_start" in named
    assert "recorder.py" in named["record_start"]["reason"]
    assert named["record_start"]["substitute"], "an unobservable hop must name its substitute"
    # The honest consequence: the cycle still finishes on the signals it *can*
    # read (editor-open + artifact) — it does not fail, and it does not pretend.
    assert report["ok"] is True
    assert steps["stop_and_open_editor"]["status"] == "observed"
    assert steps["export_video"]["status"] == "observed"


def test_a_pre_open_editor_cannot_prove_this_finalize(qapp, tmp_path):
    """A second cycle on the same app session: a pre-open editor is not a signal."""
    from PIL import Image

    images = tmp_path / "source"
    images.mkdir()
    left = images / "left.png"
    Image.new("RGB", (64, 48), (10, 10, 10)).save(left)
    page = _ic_page(qapp)
    app = _FakeApp(
        handlers=_handlers(tmp_path, page=page.page),
        store=page.store,
        out_dir=tmp_path / "cycle",
        emit_recording_trace=False,
    )
    app.editor_open = True  # left open by a previous cycle
    cycle = SceneCycle(
        channel=app, out_dir=tmp_path / "cycle", clock=app.clock, sleep=app.clock.sleep
    )
    report = cycle.run(left, left)

    step = _steps(report)["stop_and_open_editor"]
    assert step["status"] == "unobservable"
    assert "already open" in step["detail"]
    named = {row["step"] for row in report["unobservable"]}
    assert "stop_and_open_editor" in named


def test_a_scene_without_a_loupe_fails_by_name_when_the_toggle_creates_none(qapp, tmp_path):
    """The command vocabulary adjusts instances; creating one is a toggle."""
    from PIL import Image

    images = tmp_path / "source"
    images.mkdir()
    left = images / "left.png"
    Image.new("RGB", (64, 48), (10, 10, 10)).save(left)
    page = _ic_page(qapp, loupes=0)
    app = _FakeApp(
        handlers=_handlers(tmp_path, page=page.page),
        store=page.store,
        out_dir=tmp_path / "cycle",
        magnifier_toggle_creates=False,
    )
    cycle = SceneCycle(
        channel=app, out_dir=tmp_path / "cycle", clock=app.clock, sleep=app.clock.sleep,
        wait_s=5.0,
    )
    report = cycle.run(left, left)

    assert report["ok"] is False
    steps = _steps(report)
    assert steps["build_scene"]["status"] == "failed"
    assert "multi-instance UI mode" in steps["build_scene"]["detail"]
    assert steps["capture_png"]["status"] == "skipped"
    assert steps["export_video"]["status"] == "skipped"


# ---------------------------------------------------------------------------
# (b) the PNG is byte-stable across two runs — and drift is detected
# ---------------------------------------------------------------------------


def test_png_is_byte_stable_across_two_runs_of_the_same_scene(qapp, tmp_path):
    from PIL import Image

    images = tmp_path / "source"
    images.mkdir()
    left = images / "left.png"
    Image.new("RGB", (64, 48), (12, 34, 56)).save(left)

    def one_run(name: str, **kwargs):
        page = _ic_page(qapp)
        app = _FakeApp(
            handlers=_handlers(tmp_path, page=page.page),
            store=page.store,
            out_dir=tmp_path / name,
        )
        cycle = SceneCycle(
            channel=app,
            out_dir=tmp_path / name,
            clock=app.clock,
            sleep=app.clock.sleep,
            **kwargs,
        )
        return cycle.run(left, left)

    first = one_run("run1")
    second = one_run("run2", baseline=first)

    assert first["ok"] and second["ok"], (first["failures"], second["failures"])
    assert first["artifacts"]["png"]["sha256"] == second["artifacts"]["png"]["sha256"]
    assert second["determinism"]["png"]["verdict"] == "byte_stable"
    assert first["determinism"]["png"]["verdict"] == "unknown", (
        "without a baseline the tool must not claim reproducibility"
    )


def test_png_drift_against_a_baseline_is_a_failure_not_a_pass(qapp, tmp_path):
    from PIL import Image

    images = tmp_path / "source"
    images.mkdir()
    left = images / "left.png"
    Image.new("RGB", (64, 48), (12, 34, 56)).save(left)

    page = _ic_page(qapp)
    baseline_app = _FakeApp(
        handlers=_handlers(tmp_path, page=page.page), store=page.store, out_dir=tmp_path / "a"
    )
    baseline = SceneCycle(
        channel=baseline_app, out_dir=tmp_path / "a",
        clock=baseline_app.clock, sleep=baseline_app.clock.sleep,
    ).run(left, left)

    page = _ic_page(qapp)
    drift_app = _FakeApp(
        handlers=_handlers(tmp_path, page=page.page),
        store=page.store,
        out_dir=tmp_path / "b",
        render_variant=7,
    )
    report = SceneCycle(
        channel=drift_app, out_dir=tmp_path / "b",
        clock=drift_app.clock, sleep=drift_app.clock.sleep, baseline=baseline,
    ).run(left, left)

    assert report["ok"] is False
    assert report["determinism"]["png"]["verdict"] == "differs"
    assert [row["kind"] for row in report["failures"]] == ["png_not_reproducible"]
    assert report["failures"][0]["last_observed"]["baseline_sha256"] == (
        baseline["artifacts"]["png"]["sha256"]
    )


# ---------------------------------------------------------------------------
# (c) the video is reported non-deterministic unless a frame count is pinned
# ---------------------------------------------------------------------------


def test_video_is_reported_non_deterministic_with_the_wall_clock_reason(app_and_inputs):
    report, _out = _run(app_and_inputs.app, app_and_inputs)
    video = report["determinism"]["video"]

    assert video["pinned"] is False
    assert video["observed_frames"] == app_and_inputs.app.frames
    assert "recorder.py" in video["reason"]
    assert "wall" in video["reason"] or "wall-clock" in video["reason"]
    assert report["ok"] is True, "not promising determinism is not a failure"


def test_a_pinned_frame_count_is_compared_not_assumed(app_and_inputs):
    report, _out = _run(
        app_and_inputs.app, app_and_inputs, expect_video_frames=app_and_inputs.app.frames
    )
    video = report["determinism"]["video"]
    assert video["pinned"] is True
    assert video["observed_frames"] == app_and_inputs.app.frames
    assert "pinned by the caller" in video["reason"]
    assert report["ok"] is True


def test_a_wrong_pinned_frame_count_fails_the_export_hop(app_and_inputs):
    report, _out = _run(
        app_and_inputs.app, app_and_inputs, expect_video_frames=app_and_inputs.app.frames + 5
    )
    assert report["ok"] is False
    assert _steps(report)["export_video"]["status"] == "failed"
    assert "pinned frame count mismatch" in report["failures"][0]["message"]


# ---------------------------------------------------------------------------
# (d) a timeout surfaces the last observed state, never a pass
# ---------------------------------------------------------------------------


def test_export_timeout_surfaces_the_last_observed_state(qapp, tmp_path):
    from PIL import Image

    images = tmp_path / "source"
    images.mkdir()
    left = images / "left.png"
    Image.new("RGB", (64, 48), (12, 34, 56)).save(left)
    page = _ic_page(qapp)
    app = _FakeApp(
        handlers=_handlers(tmp_path, page=page.page),
        store=page.store,
        out_dir=tmp_path / "cycle",
        fail_export=True,
    )
    report = SceneCycle(
        channel=app,
        out_dir=tmp_path / "cycle",
        clock=app.clock,
        sleep=app.clock.sleep,
        export_s=30.0,
    ).run(left, left)

    assert report["ok"] is False
    failure = report["failures"][0]
    assert failure["step"] == "export_video"
    assert failure["kind"] == "timeout"
    assert failure["polls"] > 0
    last = json.dumps(failure["last_observed"], sort_keys=True)
    assert "FFmpeg exited with error code 1" in last, (
        "the timeout must carry what was actually observed"
    )
    assert "Rendering 42 frames" in last
    assert report["artifacts"]["video"] is None, "a timed-out encode has no artifact"
    # The HTML-ish claim we must never make: a video hop "observed" on a timeout.
    assert _steps(report)["export_video"]["status"] == "failed"


def test_the_cli_writes_a_report_and_exits_non_zero_on_a_failed_cycle(qapp, tmp_path):
    from PIL import Image

    images = tmp_path / "source"
    images.mkdir()
    left = images / "left.png"
    Image.new("RGB", (64, 48), (1, 2, 3)).save(left)
    page = _ic_page(qapp)
    app = _FakeApp(
        handlers=_handlers(tmp_path, page=page.page),
        store=page.store,
        out_dir=tmp_path / "cycle",
        fail_export=True,
    )
    out_dir = tmp_path / "cli-out"
    code = main(
        [
            "--image-a", str(left),
            "--image-b", str(left),
            "--out", str(out_dir),
            "--export-s", "30",
            "--json",
        ],
        client=app,
        clock=app.clock,
        sleep=app.clock.sleep,
    )

    assert code == 1
    report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["schema"] == cycle_mod.SCHEMA
    assert report["failures"][0]["step"] == "export_video"


def test_dry_run_prints_the_signals_and_sends_nothing(capsys):
    code = main(["--dry-run"])
    output = capsys.readouterr().out

    assert code == 0
    assert "dry-run: nothing was sent" in output
    for hop in ("load_pair", "verify_scene", "capture_png", "record_start", "export_video"):
        assert hop in output
    assert "video_export_job" in output and "jobs.py" in output
