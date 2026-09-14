"""Immediate-overlay pilot: statelessness contract (Engine Phase 3).

The three annotation passes (guides / divider / capture) resolve their
per-frame draw decisions through ctx-first pure functions in their
``overlay_model`` modules. This file pins the pilot:

* the pilot modules hold no pipeline/buffer state (no QRhi / buffer /
  pipeline names, no ``self``, no module-level mutable state), import
  no ``store`` code, and branch on no export mode;
* every public resolver takes the frame context first and returns
  frozen plain data;
* resolvers are pure (repeat calls equal, frozen outputs, documented
  source priority) and the pass shells delegate to them without
  changing behavior.

Deliberately retained (not failures): each pass keeps its
``initialize``-owned GPU shell (pipelines/buffers), ``prepare`` →
``resource_updates`` staging, and the Phase-2-pinned ``record()``
``widget.*`` reads — see
``tests/contracts/test_pass_reads_only_ctx.py`` ("ctx plus its own
retained GPU resources") and
``test_canvas_fullscreen_pass_resources_single_owner.py``.
"""

from __future__ import annotations

import ast
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor

FEATURES = Path(__file__).resolve().parents[2] / "canvas" / "features"
PILOT_MODULES = {
    "guides": FEATURES / "guides" / "overlay_model.py",
    "divider": FEATURES / "divider" / "overlay_model.py",
    "capture": FEATURES / "capture" / "overlay_model.py",
}

_PIPELINE_BUFFER_TOKENS = ("QRhi", "QShader", "Buffer", "Pipeline", "uniform_buffers", "srbs")


def _parse(name):
    path = PILOT_MODULES[name]
    assert path.is_file(), f"pilot module missing: {path}"
    return path, ast.parse(path.read_text(encoding="utf-8"))


def _public_functions(tree):
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]


# ---------------------------------------------------------------------------
# Static shape: ctx-first, no store, no export branches, no GPU state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(PILOT_MODULES))
def test_pilot_resolvers_are_ctx_first(name):
    _, tree = _parse(name)
    funcs = _public_functions(tree)
    assert funcs, f"{name}/overlay_model.py defines no public resolver"
    for func in funcs:
        args = [a.arg for a in func.args.args]
        assert args and args[0] == "ctx", (
            f"{name}/overlay_model.py:{func.lineno} {func.name}{tuple(args)} — "
            f"pilot resolvers take the frame context first"
        )


@pytest.mark.parametrize("name", sorted(PILOT_MODULES))
def test_pilot_module_imports_no_store(name):
    """Pilot resolvers never touch the Redux store — they read only ctx."""
    path, tree = _parse(name)
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods = [node.module or ""]
        else:
            continue
        for mod in mods:
            top = mod.split(".")[0]
            if top in ("core", "store") or mod.startswith(
                ("core.", "store.", "plugins.")
            ):
                offenders.append(f"{path}:{node.lineno} imports {mod}")
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


@pytest.mark.parametrize("name", sorted(PILOT_MODULES))
def test_pilot_module_has_no_export_mode_branch(name):
    _, tree = _parse(name)
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        names = {c.id for c in ast.walk(node) if isinstance(c, ast.Name)}
        lits = {c.value for c in ast.walk(node) if isinstance(c, ast.Constant)}
        if "mode" in names and "export" in lits:
            hits.append(f"line {node.lineno}")
    assert not hits, f"{name}/overlay_model.py branches on export mode: {hits}"


@pytest.mark.parametrize("name", sorted(PILOT_MODULES))
def test_pilot_module_holds_no_pipeline_or_buffer_state(name):
    _, tree = _parse(name)
    # Identifier scan (not raw text: docstrings may name what is absent).
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
    token_hits = sorted(
        {ident for ident in identifiers for tok in _PIPELINE_BUFFER_TOKENS if tok in ident}
    )
    assert not token_hits, (
        f"{name}/overlay_model.py uses pipeline/buffer state: {token_hits}"
    )
    self_hits = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ]
    assert not self_hits, (
        f"{name}/overlay_model.py uses 'self' at lines {self_hits} — "
        f"pilot resolvers are module-level pure functions"
    )
    # No module-level mutable state: only UPPER_CASE constants, __all__,
    # imports, docstrings, defs.
    mutable = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and (
                    target.id.startswith("__") or target.id == "__all__"
                ):
                    continue
                if isinstance(target, ast.Name) and target.id.isupper():
                    continue
                mutable.append(f"line {node.lineno}: {ast.unparse(target)}")
    assert not mutable, (
        f"{name}/overlay_model.py has module-level mutable state:\n  - "
        + "\n  - ".join(mutable)
    )


@pytest.mark.parametrize("name", sorted(PILOT_MODULES))
def test_pilot_outputs_are_frozen_dataclasses(name):
    _, tree = _parse(name)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    assert classes, f"{name}/overlay_model.py defines no output dataclass"
    for cls in classes:
        deco = ast.unparse(cls.decorator_list[0]) if cls.decorator_list else ""
        assert "dataclass" in deco, f"{cls.name} is not a dataclass"
        assert "frozen=True" in deco, f"{cls.name} is not frozen"


# ---------------------------------------------------------------------------
# Fixtures: fake frame contexts (identity projection at zoom=1/pan=0)
# ---------------------------------------------------------------------------


def _base_ctx(**overrides):
    ctx = SimpleNamespace(
        width=100,
        height=100,
        canvas_width=100,
        canvas_height=100,
        canvas_offset_x=0.0,
        canvas_offset_y=0.0,
        zoom_level=1.0,
        resolved_style=SimpleNamespace(
            annotation_line_stroke_px=2.0,
            annotation_ring_stroke_px=2.0,
        ),
        scene_frame=SimpleNamespace(
            feature_payloads={},
            single_image_preview=0,
        ),
        feature_overlay=SimpleNamespace(capture_circles=()),
        widget=None,
    )
    for key, value in overrides.items():
        setattr(ctx, key, value)
    return ctx


def _base_widget(**overrides):
    widget = SimpleNamespace(
        runtime_state=SimpleNamespace(
            _guide_sets=[],
            _capture_circles=[],
        ),
    )
    for key, value in overrides.items():
        setattr(widget, key, value)
    return widget


# ---------------------------------------------------------------------------
# Guides: pure span resolution
# ---------------------------------------------------------------------------


def _guides_ctx_widget():
    widget = _base_widget()
    widget.runtime_state._guide_sets = [
        (
            QPointF(10.0, 20.0),  # capture center
            5.0,  # capture radius
            (QPointF(70.0, 80.0),),  # target centers
            (4.0,),  # target radii
            QColor(255, 0, 0, 255),
        )
    ]
    return _base_ctx(), widget


def test_guides_resolve_is_pure_and_frozen():
    from tabs.image_compare.canvas.features.guides.overlay_model import (
        resolve_guide_spans,
    )

    ctx, widget = _guides_ctx_widget()
    first = resolve_guide_spans(ctx, widget, matrix=None)
    second = resolve_guide_spans(ctx, widget, matrix=None)
    assert first == second and len(first) == 1
    span = first[0]
    # Identity projection at zoom=1/pan=0: screen == widget px (float noise).
    assert (span.start_x, span.start_y) == pytest.approx((70.0, 80.0))
    assert (span.end_x, span.end_y) == pytest.approx((10.0, 20.0))
    assert span.start_radius == 4.0 and span.end_radius == 5.0
    assert span.line_width == 2.0
    assert (span.red, span.green, span.blue, span.alpha) == (1.0, 0.0, 0.0, 1.0)
    with pytest.raises(Exception):
        span.start_x = 0.0  # frozen output


def test_guides_resolve_empty_and_scales_with_zoom():
    from tabs.image_compare.canvas.features.guides.overlay_model import (
        resolve_guide_spans,
    )

    ctx, widget = _guides_ctx_widget()
    widget.runtime_state._guide_sets = []
    assert resolve_guide_spans(ctx, widget, matrix=None) == ()

    widget.runtime_state._guide_sets = _guides_ctx_widget()[1].runtime_state._guide_sets
    ctx.zoom_level = 2.0
    (span,) = resolve_guide_spans(ctx, widget, matrix=None)
    assert span.start_radius == 8.0 and span.end_radius == 10.0


def test_guides_pass_prepares_from_resolver():
    """GuidesPass.prepare packs exactly the resolver's spans (no fork)."""
    from tabs.image_compare.canvas.features.guides.overlay_model import (
        resolve_guide_spans,
    )
    from tabs.image_compare.canvas.features.guides.passes import (
        GuidesPass,
        _UNIFORM_FMT,
    )

    ctx, widget = _guides_ctx_widget()
    ctx.widget = widget
    matrix = tuple([1.0 if i % 5 == 0 else 0.0 for i in range(16)])
    (span,) = resolve_guide_spans(ctx, widget, matrix)
    expected = struct.pack(
        _UNIFORM_FMT,
        *matrix,
        100.0,
        100.0,
        span.start_x,
        span.start_y,
        span.end_x,
        span.end_y,
        span.start_radius,
        span.end_radius,
        span.line_width,
        0.0,
        0.0,
        0.0,
        span.red,
        span.green,
        span.blue,
        span.alpha,
    )
    assert len(expected) == 128

    calls = []

    class FakeRhi:
        def clipSpaceCorrMatrix(self):
            m = SimpleNamespace(data=lambda: list(matrix))
            return m

    class FakeResources:
        rhi = FakeRhi()

        def ensure_items(self, n):
            calls.append(("ensure", n))

        def prepare_vertex_buffer(self, updates):
            calls.append(("vertex", True))

        uniform_buffers = [object()]

    fnord = GuidesPass()
    fnord.resources = FakeResources()

    class Updates:
        def __init__(self):
            self.blocks = []

        def updateDynamicBuffer(self, buf, offset, block):
            self.blocks.append(block)

    updates = Updates()
    fnord.prepare(widget, ctx, updates)
    assert updates.blocks == [expected]
    assert ("ensure", 1) in calls


# ---------------------------------------------------------------------------
# Divider: pure spec resolution
# ---------------------------------------------------------------------------


def _divider_ctx_widget(*, split=0.25, thickness=3, horizontal=False):
    ctx = _base_ctx(
        scene_frame=SimpleNamespace(
            feature_payloads={
                "show_divider": True,
                "divider_thickness": thickness,
                "divider_color": QColor(0, 255, 0, 255),
            },
            is_horizontal=horizontal,
            split_position_visual=split,
            split_override=None,
            content_rect_px=(0, 0, 100, 100),
        )
    )
    widget = SimpleNamespace(runtime_state=None)  # forces canvas-dim fallback clip
    return ctx, widget


def test_divider_resolve_is_pure_and_clamped():
    from tabs.image_compare.canvas.features.divider.overlay_model import (
        resolve_divider_spec,
    )

    ctx, widget = _divider_ctx_widget(split=0.25)
    first = resolve_divider_spec(ctx, widget)
    assert resolve_divider_spec(ctx, widget) == first
    assert first.show is True and first.thickness_px == 3.0
    assert first.is_horizontal is False
    # Fallback clip = canvas dims -> vertical line at 100 * 0.25.
    assert (first.clip_x, first.clip_y, first.clip_w, first.clip_h) == (0.0, 0.0, 100.0, 100.0)
    assert first.position_px == pytest.approx(25.0)
    assert (first.red, first.green, first.blue, first.alpha) == (0.0, 1.0, 0.0, 1.0)
    with pytest.raises(Exception):
        first.position_px = 0.0  # frozen output

    over, _ = _divider_ctx_widget(split=1.5)
    assert resolve_divider_spec(over, widget).position_px == pytest.approx(100.0)
    under, _ = _divider_ctx_widget(split=-2.0)
    assert resolve_divider_spec(under, widget).position_px == pytest.approx(0.0)


def test_divider_override_and_orientation():
    from tabs.image_compare.canvas.features.divider.overlay_model import (
        content_split_visual,
        resolve_divider_spec,
    )

    ctx, widget = _divider_ctx_widget(split=0.25)
    ctx.scene_frame.split_override = 0.75
    assert content_split_visual(ctx) == pytest.approx(0.75)
    assert resolve_divider_spec(ctx, widget).position_px == pytest.approx(75.0)

    horiz_ctx, horiz_widget = _divider_ctx_widget(split=0.5, horizontal=True)
    spec = resolve_divider_spec(horiz_ctx, horiz_widget)
    assert spec.is_horizontal is True
    assert spec.position_px == pytest.approx(50.0)


def test_divider_pass_delegates_to_resolver():
    from tabs.image_compare.canvas.features.divider.overlay_model import (
        resolve_divider_spec,
    )
    from tabs.image_compare.canvas.features.divider.passes import DividerPass

    ctx, widget = _divider_ctx_widget(split=0.25)
    ctx.widget = widget
    spec = resolve_divider_spec(ctx, widget)
    show, position, thickness, horizontal, color, clip = DividerPass._resolve_divider_state(
        widget, ctx
    )
    assert (show, position, thickness, horizontal) == (
        spec.show,
        spec.position_px,
        spec.thickness_px,
        spec.is_horizontal,
    )
    assert (color.redF(), color.greenF(), color.blueF(), color.alphaF()) == (
        spec.red,
        spec.green,
        spec.blue,
        spec.alpha,
    )
    assert clip == (spec.clip_x, spec.clip_y, spec.clip_w, spec.clip_h)


# ---------------------------------------------------------------------------
# Capture: pure ring resolution + source priority
# ---------------------------------------------------------------------------


def test_capture_resolve_priority_and_purity():
    from tabs.image_compare.canvas.features.capture.overlay_model import (
        resolve_capture_circles,
        resolve_capture_rings,
    )

    overlay_circle = (QPointF(1.0, 2.0), 3.0, QColor(255, 255, 255, 255))
    payload_circle = (QPointF(4.0, 5.0), 6.0, QColor(255, 255, 255, 255))
    runtime_circle = (QPointF(7.0, 8.0), 9.0, QColor(255, 255, 255, 255))

    ctx = _base_ctx()
    widget = _base_widget()
    widget.runtime_state._capture_circles = [runtime_circle]
    # Runtime fallback when nothing else provides circles.
    assert resolve_capture_circles(ctx, widget) == (runtime_circle,)

    ctx.scene_frame.feature_payloads = {"capture_circles": [payload_circle]}
    assert resolve_capture_circles(ctx, widget) == (payload_circle,)

    ctx.feature_overlay = SimpleNamespace(capture_circles=[overlay_circle])
    assert resolve_capture_circles(ctx, widget) == (overlay_circle,)

    rings = resolve_capture_rings(ctx, widget)
    assert resolve_capture_rings(ctx, widget) == rings and len(rings) == 1
    ring = rings[0]
    assert (ring.center_x, ring.center_y) == pytest.approx((1.0, 2.0))
    # radius 3 * zoom 1, shrunk by half the 2px stroke = 2.0.
    assert ring.screen_radius == pytest.approx(2.0)
    assert ring.line_width == 2.0
    assert ring.alpha == 1.0  # ring color forced fully opaque
    with pytest.raises(Exception):
        ring.center_x = 0.0  # frozen output


def test_capture_skips_degenerate_circles():
    from tabs.image_compare.canvas.features.capture.overlay_model import (
        resolve_capture_rings,
    )

    ctx = _base_ctx()
    widget = _base_widget()
    widget.runtime_state._capture_circles = [
        (None, 5.0, QColor(255, 255, 255, 255)),
        (QPointF(1.0, 1.0), 0.0, QColor(255, 255, 255, 255)),
        (QPointF(1.0, 1.0), -2.0, QColor(255, 255, 255, 255)),
    ]
    assert resolve_capture_rings(ctx, widget) == ()


def test_capture_pass_delegates_to_resolver():
    from tabs.image_compare.canvas.features.capture.overlay_model import (
        resolve_capture_circles,
    )
    from tabs.image_compare.canvas.features.capture.passes import CaptureRingPass

    ctx = _base_ctx()
    widget = _base_widget()
    widget.runtime_state._capture_circles = [
        (QPointF(3.0, 4.0), 5.0, QColor(255, 255, 255, 255))
    ]
    assert CaptureRingPass._resolve_capture_circles(widget, ctx) == resolve_capture_circles(
        ctx, widget
    )
