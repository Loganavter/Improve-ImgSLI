"""Scene commands — ``run_action(params)`` + ``set_scene_commands`` (S2).

Every case is built from **real widgets and real builders**, never from a fake
scene: the Image Compare canvas is a real ``CanvasWidget`` whose scene graph is
produced by the real ``build_magnifier_objects`` / ``build_magnifier_layout``,
and the Multi Compare canvas is a real ``MultiCompareCanvasWidget`` whose
composition comes from the app's own ``_rebuild_composition`` (which calls
``build_composition_plan`` + ``resolve_composition``). Commands run through the
canvas features' own command registry (``viewport.set_instance_visibility``,
``divider.viewport.set_thickness``) and the tab's own Redux dispatch
(``multi_compare/set_split_weights``).

Falsification: none of this exists on the pre-change tree — ``run_action`` has
no params, ``set_scene_commands`` is not a method/tool, ``scene_commands.py`` and
``devtools/canvas_scene/commands.py`` are absent, and no scene test drives a
command. Each test below therefore fails on the pre-change tree at the first
scene-command call (proven RED; see ``DONE.md``).

Contract points covered:

* (a) an unknown / mistyped / out-of-range param is refused **with the schema in
  the hint**, and nothing is applied;
* (b) an ordered list stops at the first error — the later commands did not run;
* (c) verify=True fails a command that ran but changed nothing;
* (d) a value-taking command is idempotent: the same command twice lands in the
  same state (and the second verified run is the honest "changed nothing");
* (e) verification re-reads through the S1 read verb (``scene_read.
  read_canvas_scene``), counted — one scene source, two consumers;
* (f) Multi Compare split weights verify against the projected composition;
* (g) the command path never mutates the Store directly (AST contract);
* (h) an MCP tool surface for the ordered list + ``run_action`` params.

Runs offscreen only (the supervisor runs the live proof).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QWidget

from core.control import scene_read
from core.control.discovery import MethodError
from core.control.handlers import ControlHandlers
from core.store import Store
from ui.actions.registry import ActionRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from app import catalog  # noqa: E402
from app.backend import AppBackend, ToolError  # noqa: E402
from app.live import LiveBackend  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# fixtures: real canvases, real builders (same construction as the S1 tests)
# ---------------------------------------------------------------------------


def _ic_fixture(qapp):
    """A real Image Compare canvas + store with two loupes (one hidden)."""
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

    add_magnifier_model(view_state, viewport.render_config, "loupe-a")
    add_magnifier_model(view_state, viewport.render_config, "loupe-b")
    update_magnifier_model(view_state, viewport.render_config, "loupe-b", visible=False)
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


def _mc_fixture(qapp):
    """A real Multi Compare canvas driven by its own store dispatch."""
    from tabs.multi_compare.models import (
        CompareSlot,
        LeafNode,
        MultiCompareState,
        SplitNode,
    )
    from tabs.multi_compare.pipeline.cache import MultiComparePixelCache
    from tabs.multi_compare.scene.store import MultiCompareStore
    from tabs.multi_compare.ui.canvas_widget import MultiCompareCanvasWidget

    state = MultiCompareState(
        slots=[
            CompareSlot(id=1, path=Path("/fixtures/left.png"), label="left"),
            CompareSlot(id=2, path=Path("/fixtures/right.png"), label="right"),
        ],
        root=SplitNode(
            direction="h", children=[LeafNode(1), LeafNode(2)], weights=[0.6, 0.4]
        ),
    )
    store = MultiCompareStore(initial=state)
    canvas = MultiCompareCanvasWidget()
    canvas.resize(900, 500)
    cache = MultiComparePixelCache()
    for fixture in ("/fixtures/left.png", "/fixtures/right.png"):
        image = QImage(64, 48, QImage.Format.Format_RGB32)
        image.fill(QColor("#3366cc"))
        cache.put_preview(fixture, image)
    canvas.pixel_cache = cache
    # The tab wires exactly these two (widget.py: set_dispatch + set_state).
    canvas.set_dispatch(store.dispatch)
    canvas.set_state(store.state)
    canvas._rebuild_composition()
    assert canvas._active_composition is not None, "fixture must resolve a composition"

    page = QWidget()
    canvas.setParent(page)
    return SimpleNamespace(store=store, canvas=canvas, page=page)


def _handlers(tmp_path, *, page, kinds=("image_compare", "multi_compare")):
    def _tab():
        class _Contract:
            def get_canvas_geometry_provider(self):
                return SimpleNamespace()

        return _Contract()

    handlers = ControlHandlers(
        window=SimpleNamespace(store=None),
        app=None,
        artifacts_dir=tmp_path / "artifacts",
        registry_provider=lambda: ActionRegistry(),
    )
    handlers._tabs = lambda: [(kind, _tab()) for kind in kinds]  # type: ignore[assignment]
    # One page per test; the read verb's own discovery seam is pinned to it,
    # so both consumers (get_canvas_scene and the verifier) see one canvas.
    scene_read.page_widget = lambda _handlers, _kind: page  # type: ignore[assignment]
    return handlers


def _scene(handlers, tab: str) -> dict:
    return handlers.handle("get_canvas_scene", {"tab": tab})


def _same_scene(left: dict, right: dict) -> bool:
    return scene_read.canonical_json(left) == scene_read.canonical_json(right)


# ---------------------------------------------------------------------------
# (a) typed params: unknown key / wrong type / out of range → refused + schema
# ---------------------------------------------------------------------------


def test_unknown_param_key_is_refused_with_the_schema_in_the_hint(qapp, tmp_path):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)
    before = _scene(handlers, "image_compare")

    with pytest.raises(MethodError) as excinfo:
        handlers.handle(
            "run_action",
            {
                "action_id": "magnifier.set_visible",
                "tab": "image_compare",
                "params": {"id": "loupe-b", "visibl": True},
            },
        )

    assert "unknown param" in excinfo.value.message
    assert "visibl" in excinfo.value.message
    hint = excinfo.value.hint or ""
    # The schema travels in the error: the caller never has to guess.
    assert "magnifier.set_visible" in hint
    assert "id: a string" in hint and "visible: true or false" in hint
    assert "\"visible\": false" in hint, "the hint carries a runnable example"
    assert _same_scene(_scene(handlers, "image_compare"), before), "nothing was applied"


@pytest.mark.parametrize(
    "params, fragment",
    [
        ({"id": "loupe-b", "visible": "yes"}, "must be true or false"),
        ({"id": "loupe-b"}, "missing required param 'visible'"),
        ({"id": "loupe-b", "visible": True, "size": 0.3}, "unknown param"),
    ],
)
def test_mistyped_and_missing_params_are_refused(qapp, tmp_path, params, fragment):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    with pytest.raises(MethodError) as excinfo:
        handlers.handle(
            "run_action",
            {
                "action_id": "magnifier.set_visible",
                "tab": "image_compare",
                "params": params,
            },
        )

    assert fragment in excinfo.value.message
    assert "magnifier.set_visible(" in (excinfo.value.hint or "")


def test_out_of_range_value_is_refused_with_bounds_in_the_hint(qapp, tmp_path):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    with pytest.raises(MethodError) as excinfo:
        handlers.handle(
            "run_action",
            {
                "action_id": "magnifier.set_size",
                "tab": "image_compare",
                "params": {"id": "loupe-a", "size": 5.0},
            },
        )

    assert "must be <= 1.0" in excinfo.value.message
    assert "[0.01..1.0]" in (excinfo.value.hint or "")


def test_find_actions_still_refuse_params_instead_of_ignoring_them(tmp_path):
    handlers = _handlers(tmp_path, page=None, kinds=("image_compare",))

    with pytest.raises(MethodError) as excinfo:
        handlers.handle(
            "run_action",
            {"action_id": "platform.settings", "params": {"whatever": 1}},
        )

    assert "takes no params" in excinfo.value.message
    assert "magnifier.set_visible" in (excinfo.value.hint or "")


# ---------------------------------------------------------------------------
# (b) an ordered list stops at the first error
# ---------------------------------------------------------------------------


def test_ordered_list_stops_at_the_first_error(qapp, tmp_path):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    outcome = handlers.handle(
        "set_scene_commands",
        {
            "tab": "image_compare",
            "commands": [
                {
                    "action": "divider.set_thickness",
                    "params": {"thickness": 6},
                    "expect": {"dividers[0].thickness": 6},
                },
                {
                    "action": "magnifier.set_visible",
                    "params": {"id": "no-such-loupe", "visible": True},
                    "expect": {"magnifiers[0].visible": True},
                },
                {
                    "action": "divider.set_visible",
                    "params": {"visible": False},
                    "expect": {"dividers[0].visible": False},
                },
            ],
        },
    )

    assert outcome["ok"] is False
    assert outcome["stopped_at"] == 1, "the run stops at the failing command"
    assert outcome["count"] == 1, "only the first command is applied"
    assert [row["action"] for row in outcome["applied"]] == ["divider.set_thickness"]
    error = outcome["error"]
    assert error["index"] == 1 and error["kind"] == "invalid_command"
    assert "no magnifier instance" in error["message"]
    assert "loupe-a" in (error["hint"] or ""), "the hint lists the real instances"

    scene = _scene(handlers, "image_compare")
    assert scene["dividers"][0]["thickness"] == 6.0, "the first command did run"
    assert scene["dividers"][0]["visible"] is True, "the third command did NOT run"
    assert outcome["scene"]["dividers"][0]["thickness"] == 6.0


def test_command_aimed_at_the_wrong_canvas_is_refused(qapp, tmp_path):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    outcome = handlers.handle(
        "set_scene_commands",
        {
            "tab": "image_compare",
            "commands": [
                # A Multi Compare command against an Image Compare scene: refuse,
                # never half-apply against the wrong tree.
                {
                    "action": "layout.set_split_weights",
                    "params": {"path": [], "weights": [0.5, 0.5]},
                    "expect": {"dividers[0].pos": 0.0},
                }
            ],
        },
    )

    assert outcome["ok"] is False
    assert outcome["stopped_at"] == 0
    assert "applies to a mc_projection scene" in outcome["error"]["message"]


# ---------------------------------------------------------------------------
# (c) verify=True fails a command that changed nothing
# ---------------------------------------------------------------------------


def test_verify_fails_when_the_command_changed_nothing(qapp, tmp_path):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)
    # ``loupe-b`` starts hidden, so setting it hidden again is a value-taking
    # no-op — and "it ran" must not pass for "it happened".
    assert _scene(handlers, "image_compare")["magnifiers"][1]["visible"] is False

    outcome = handlers.handle(
        "set_scene_commands",
        {
            "tab": "image_compare",
            "commands": [
                {
                    "action": "magnifier.set_visible",
                    "params": {"id": "loupe-b", "visible": False},
                    "expect": {"magnifiers[1].visible": False},
                }
            ],
        },
    )

    assert outcome["ok"] is False
    assert outcome["stopped_at"] == 0
    assert outcome["applied"][0]["changed_count"] == 0
    assert outcome["applied"][0]["verified"] is False
    error = outcome["error"]
    assert error["kind"] == "verification_failed"
    assert "changed nothing" in error["message"]


def test_verify_without_expect_is_refused_by_schema(qapp, tmp_path):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    outcome = handlers.handle(
        "set_scene_commands",
        {
            "tab": "image_compare",
            "commands": [
                {"action": "divider.set_visible", "params": {"visible": False}}
            ],
        },
    )

    assert outcome["ok"] is False
    assert outcome["stopped_at"] == 0
    assert "needs expect" in outcome["error"]["message"]
    hint = outcome["error"]["hint"] or ""
    assert "divider.set_visible(visible: true or false)" in hint, "the schema is in the hint"
    assert "expect example" in hint
    assert _scene(handlers, "image_compare")["dividers"][0]["visible"] is True


def test_a_declared_value_the_scene_does_not_reach_is_a_failure(qapp, tmp_path):
    """expect is checked against the re-read scene, not against the intent."""
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    outcome = handlers.handle(
        "set_scene_commands",
        {
            "tab": "image_compare",
            "commands": [
                {
                    "action": "divider.set_thickness",
                    "params": {"thickness": 6},
                    # The command ran (thickness is 6), but the declared value is
                    # not what the scene reports.
                    "expect": {"dividers[0].thickness": 7},
                }
            ],
        },
    )

    assert outcome["ok"] is False
    assert outcome["error"]["kind"] == "verification_failed"
    assert "dividers[0].thickness: expected 7" in outcome["error"]["message"]
    assert "scene reports 6.0" in outcome["error"]["message"]
    assert _scene(handlers, "image_compare")["dividers"][0]["thickness"] == 6.0


def test_a_change_outside_the_declared_scope_is_a_failure(qapp, tmp_path):
    """The scope guard: a command may not silently move unrelated scene state.

    Proven on a *real* scene diff (a divider command's before/after) with the
    scope narrowed to the magnifier subtree: the verifier must reject it. This
    is the guard that makes the Multi Compare command declare ``canvas`` and
    ``transform`` — its projection changes when the split does.
    """
    from core.control import scene_commands

    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)
    before = _scene(handlers, "image_compare")
    handlers.handle(
        "run_action",
        {
            "action_id": "divider.set_thickness",
            "tab": "image_compare",
            "params": {"thickness": 6},
        },
    )
    after = _scene(handlers, "image_compare")
    changed = scene_commands.scene_changes(before, after)
    assert "dividers[0].thickness" in changed

    spec = {
        "params": {},
        "scope": ("magnifiers", "sources", "unavailable"),
    }
    failure = scene_commands.verify_command(
        spec, {}, after, {"dividers[0].pos": after["dividers"][0]["pos"]}, changed
    )

    assert failure is not None
    assert any(
        "does not declare" in problem and "dividers[0].thickness" in problem
        for problem in failure["problems"]
    )


# ---------------------------------------------------------------------------
# (d) idempotent: the same command twice lands in the same state
# ---------------------------------------------------------------------------


def test_the_same_command_twice_lands_in_the_same_state(qapp, tmp_path):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)
    command = {
        "action": "magnifier.set_position",
        "params": {"id": "loupe-b", "x": 0.25, "y": 0.75},
        "expect": {"magnifiers[1].model.position_relative": [0.25, 0.75]},
    }

    first = handlers.handle(
        "set_scene_commands", {"tab": "image_compare", "commands": [command]}
    )
    assert first["ok"] is True and first["verified"] is True
    after_first = _scene(handlers, "image_compare")

    second = handlers.handle(
        "set_scene_commands", {"tab": "image_compare", "commands": [command]}
    )

    # Value-taking, not a toggle: the state is identical...
    assert _same_scene(_scene(handlers, "image_compare"), after_first)
    # ...and the honest verdict on re-running it is "nothing changed".
    assert second["ok"] is False
    assert second["stopped_at"] == 0
    assert second["applied"][0]["changed_count"] == 0
    assert "changed nothing" in second["error"]["message"]


def test_divider_commands_are_idempotent_too(qapp, tmp_path):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    for _attempt in range(2):
        handlers.handle(
            "run_action",
            {
                "action_id": "divider.set_thickness",
                "tab": "image_compare",
                "params": {"thickness": 5},
            },
        )

    scene = _scene(handlers, "image_compare")
    assert scene["dividers"][0]["thickness"] == 5.0


# ---------------------------------------------------------------------------
# (e) verification re-reads through the S1 read verb
# ---------------------------------------------------------------------------


def test_verify_re_reads_through_the_read_verb(qapp, tmp_path, monkeypatch):
    fixture = _ic_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)
    real_read = scene_read.read_canvas_scene
    calls: list[dict] = []

    def _counting_read(handlers_arg, params):
        calls.append(dict(params))
        return real_read(handlers_arg, params)

    monkeypatch.setattr(scene_read, "read_canvas_scene", _counting_read)

    outcome = handlers.handle(
        "set_scene_commands",
        {
            "tab": "image_compare",
            "commands": [
                {
                    "action": "divider.set_thickness",
                    "params": {"thickness": 5},
                    "expect": {"dividers[0].thickness": 5},
                },
                {
                    "action": "divider.set_visible",
                    "params": {"visible": False},
                    "expect": {"dividers[0].visible": False},
                },
            ],
        },
    )

    assert outcome["ok"] is True and outcome["verified"] is True
    # before + after per command, plus the final scene in the payload.
    assert len(calls) == 2 * 2 + 1, f"verification must re-read, got {len(calls)} reads"
    assert {call.get("tab") for call in calls} == {"image_compare"}

    # The same verb is what get_canvas_scene serves: one scene source, two consumers.
    before = len(calls)
    handlers.handle("get_canvas_scene", {"tab": "image_compare"})
    assert len(calls) == before + 1


# ---------------------------------------------------------------------------
# (f) Multi Compare: weights verified against the projected composition
# ---------------------------------------------------------------------------


def test_mc_split_weights_verify_against_the_projection(qapp, tmp_path):
    """A twin fixture measures the target, the other verifies against it."""
    measured = _mc_fixture(qapp)
    measured_handlers = _handlers(tmp_path, page=measured.page)
    applied = measured_handlers.handle(
        "run_action",
        {
            "action_id": "layout.set_split_weights",
            "tab": "multi_compare",
            "params": {"path": [], "weights": [0.5, 0.5]},
        },
    )
    assert applied["ran"] is True and applied["scene_command"] is True
    assert applied["verified"] is None, "no expect was declared, so nothing is verified"

    target = _scene(measured_handlers, "multi_compare")
    assert target["dividers"], "the composition still paints a split"
    divider_pos = target["dividers"][0]["pos"]
    right_width = target["panes"][1]["rect"][2]
    assert target["panes"][0]["rect"][2] == right_width, "0.5/0.5 splits evenly"

    verifying = _mc_fixture(qapp)
    verifying_handlers = _handlers(tmp_path, page=verifying.page)
    outcome = verifying_handlers.handle(
        "set_scene_commands",
        {
            "tab": "multi_compare",
            "commands": [
                {
                    "action": "layout.set_split_weights",
                    "params": {"path": [], "weights": [0.5, 0.5]},
                    "expect": {
                        "dividers[0].pos": divider_pos,
                        "panes[1].rect[2]": right_width,
                    },
                }
            ],
        },
    )

    assert outcome["ok"] is True, outcome["error"]
    assert outcome["verified"] is True
    assert _same_scene(outcome["scene"], target), (
        "the verified run lands on the state the measured run produced"
    )


def test_mc_rejects_a_path_that_is_not_a_split(qapp, tmp_path):
    fixture = _mc_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    outcome = handlers.handle(
        "set_scene_commands",
        {
            "tab": "multi_compare",
            "commands": [
                {
                    "action": "layout.set_split_weights",
                    "params": {"path": [0], "weights": [0.5]},
                    "expect": {"dividers[0].pos": 0.0},
                }
            ],
        },
    )

    assert outcome["ok"] is False
    assert "no split node at path [0]" in outcome["error"]["message"]
    assert "root = []" in (outcome["error"]["hint"] or "")


def test_mc_weight_count_must_match_the_split(qapp, tmp_path):
    fixture = _mc_fixture(qapp)
    handlers = _handlers(tmp_path, page=fixture.page)

    outcome = handlers.handle(
        "set_scene_commands",
        {
            "tab": "multi_compare",
            "commands": [
                {
                    "action": "layout.set_split_weights",
                    "params": {"path": [], "weights": [1.0]},
                    "expect": {"dividers[0].pos": 0.0},
                }
            ],
        },
    )

    assert outcome["ok"] is False
    assert "takes 2 weights, got 1" in outcome["error"]["message"]


# ---------------------------------------------------------------------------
# (g) no direct Store mutation on the command path (AST contract)
# ---------------------------------------------------------------------------


_STORE_OWNED_ROOTS = {
    "store",
    "view_state",
    "canvas_widget_state",
    "models",
    "slots",
    "root",
    "state",
    "viewport",
    "document",
    "state_slots",
}


def _mutation_targets(tree: ast.Module) -> list[str]:
    """Chains *mutated* anywhere in a module (``a.b =`` / ``a["k"] =``).

    A bare ``name = ...`` is a local binding, not a mutation, so only attribute
    and subscript targets count — the same rule the repo-wide
    ``tests/contracts/test_no_direct_store_mutation.py`` enforces.
    """
    found: list[str] = []
    for node in ast.walk(tree):
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            targets = [node.target]
        for target in targets:
            if not isinstance(target, (ast.Attribute, ast.Subscript)):
                continue
            chain: list[str] = []
            current: ast.AST = target
            while isinstance(current, (ast.Attribute, ast.Subscript)):
                if isinstance(current, ast.Attribute):
                    chain.append(current.attr)
                    current = current.value
                else:
                    current = current.value
            if isinstance(current, ast.Name):
                chain.append(current.id)
                found.append(".".join(reversed(chain)))
    return found


@pytest.mark.parametrize(
    "module_path",
    [
        "src/core/control/scene_commands.py",
        "src/devtools/canvas_scene/commands.py",
    ],
)
def test_command_path_never_mutates_store_state(module_path):
    """A command path dispatches; it never patches state behind the reducer."""
    path = REPO_ROOT / module_path
    tree = ast.parse(path.read_text(encoding="utf-8"))

    offenders = [
        chain
        for chain in _mutation_targets(tree)
        if chain.split(".")[0] in _STORE_OWNED_ROOTS
    ]

    assert not offenders, (
        f"{module_path} assigns Store/scene state directly ({offenders}) — a "
        "scene command must go through the feature command registry or the tab's "
        "dispatch, never a direct state write"
    )


def test_command_implementations_use_the_existing_command_paths():
    """The seams are the feature registry + the tab's dispatch (not re-invented)."""
    source = (REPO_ROOT / "src/devtools/canvas_scene/commands.py").read_text(
        encoding="utf-8"
    )

    assert "get_feature_command_by_alias(" in source
    assert "get_feature_command(" in source
    assert "set_split_weights(" in source
    assert 'dispatch = getattr(canvas, "_dispatch", None)' in source


def test_the_generic_command_module_names_no_tab():
    """Platform isolation: the host-neutral half stays free of tab vocabulary."""
    source = (REPO_ROOT / "src/core/control/scene_commands.py").read_text(
        encoding="utf-8"
    )

    for token in ("image_compare", "multi_compare", "tabs."):
        assert token not in source, f"scene_commands.py must not mention {token!r}"


# ---------------------------------------------------------------------------
# (h) MCP surface
# ---------------------------------------------------------------------------


def test_mcp_exposes_the_ordered_command_tool(qapp, tmp_path):
    tools = {tool["name"]: tool for tool in catalog.TOOLS}
    tool = tools["set_scene_commands"]

    assert tool["annotations"]["readOnlyHint"] is False
    assert tool["annotations"]["idempotentHint"] is True, (
        "value-taking scene commands converge on re-run"
    )
    assert tool["inputSchema"]["additionalProperties"] is False
    assert tool["inputSchema"]["required"] == ["commands"]
    assert tool["inputSchema"]["properties"]["verify"]["default"] is True
    items = tool["inputSchema"]["properties"]["commands"]["items"]
    assert set(items["properties"]) == {"action", "params", "expect"}
    assert tool["handler"] == "set_scene_commands"
    assert 200 <= len(tool["description"]) <= 500

    run = tools["run_action"]
    assert "params" in run["inputSchema"]["properties"]
    assert "expect" in run["inputSchema"]["properties"]

    backend = AppBackend(
        REPO_ROOT,
        artifacts_dir=tmp_path / "artifacts",
        data_dir=tmp_path / "data",
        snapshot_runner=lambda tab: {},
        launcher=lambda args: 1,
        settings_writer=lambda key, value: None,
    )
    with pytest.raises(ToolError) as excinfo:
        backend.set_scene_commands(commands=[], tab="image_compare")
    assert "no live instance" in str(excinfo.value)
    with pytest.raises(ToolError) as excinfo:
        backend.run_action(
            action_id="magnifier.set_visible",
            params={"id": "loupe-a", "visible": True},
        )
    assert "no live instance" in str(excinfo.value)


def test_mcp_live_proxy_forwards_commands_and_params(qapp, tmp_path):
    class _ScriptedClient:
        def __init__(self) -> None:
            self.requests: list[tuple[str, dict]] = []

        def alive(self) -> bool:
            return True

        def call(self, method, params=None, *, retry_on_timeout=False):
            self.requests.append((method, dict(params or {})))
            if method == "set_scene_commands":
                return {"ok": True, "count": 1, "applied": [], "stopped_at": None, "error": None}
            return {
                "ran": True,
                "action_id": "magnifier.set_visible",
                "tab": "image_compare",
                "scene_command": True,
                "changed": ["magnifiers[1].visible"],
                "verified": True,
                "failure": None,
            }

        def close(self) -> None:
            return None

    client = _ScriptedClient()
    live = LiveBackend()

    payload = live.set_scene_commands(
        client=client,
        commands=[{"action": "magnifier.set_visible", "params": {"id": "loupe-b", "visible": True}}],
        verify=True,
        tab="image_compare",
    )
    assert payload["ok"] is True and payload["source"] == "live"
    assert client.requests[0] == (
        "set_scene_commands",
        {
            "commands": [
                {
                    "action": "magnifier.set_visible",
                    "params": {"id": "loupe-b", "visible": True},
                }
            ],
            "verify": True,
            "tab": "image_compare",
        },
    )

    action = live.run_action(
        client=client,
        action_id="magnifier.set_visible",
        params={"id": "loupe-b", "visible": True},
        expect={"magnifiers[1].visible": True},
        tab="image_compare",
    )
    assert client.requests[1][1] == {
        "action_id": "magnifier.set_visible",
        "params": {"id": "loupe-b", "visible": True},
        "expect": {"magnifiers[1].visible": True},
        "tab": "image_compare",
    }
    assert action["scene_command"] is True
    assert action["verified"] is True
    assert action["changed"] == ["magnifiers[1].visible"]

    # A read still goes through the S1 verb's proxy path, unverified per se.
    assert "get_canvas_scene" in LiveBackend.READ_METHODS
    assert "set_scene_commands" not in LiveBackend.READ_METHODS, (
        "a mutation must never retry on a timeout"
    )
