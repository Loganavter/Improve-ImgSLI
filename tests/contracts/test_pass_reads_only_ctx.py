"""Render passes read only their context in ``record()`` — never widget/store.

Phase-2 frame-engine contract (task-engine-2abcd-2026-09-14, bucket 2C;
see docs/dev/plan_engine_design.md Phase 2 and CODE_PATTERNS.md
"Tile-engine feature checklist" item 3): ``prepare()`` writes resource
updates, ``record()`` only draws — it interprets the per-frame context
(``ctx``) plus its own retained GPU resources (``self.*``) and the draw
recorder (``command_buffer.*``). Reading widget/store state in ``record()``
re-couples the pass to the tab instead of the frame bus, and branching on
an export mode inside a pass forks live vs snapshot rendering (parity is
snapshot-replay per rendering-model.md, never ``if mode == "export"``).

Green on the current tree by construction:

* no pass ``record()`` reads ``store`` today and none branches on an
  export mode — those two rules hold at zero and stay at zero;
* viewport sizing still comes from the widget in seven passes
  (``widget.renderTarget()`` / ``widget.devicePixelRatioF``) and two
  overlay-clip flags plus one drag-drop state read — grandfathered below
  as ``_PINNED_WIDGET_READS`` (shrink-only ratchet: any NEW ``widget.*``
  chain fails, removals fail deliberately so the pin is updated on
  purpose, same idiom as ``test_no_private_grid``'s owner allowlist).
  Files that gain a ``record()`` later are held to the strict rule
  (no ``widget.*``/``store.*`` at all) — the target state for new code.

Dogma source: task-engine-2abcd-2026-09-14 (Engine W2C: frame bus).
"""

from __future__ import annotations

import ast

from ._framework import ROOT, iter_py, parse, rel

TABS = ROOT / "src" / "tabs"

#: The bus itself defines ``record()`` — it is not a pass.
_EXCLUDED_FILES = frozenset(
    {
        "src/engine/frame/context.py",
    }
)

#: Exact ``widget.*`` chains each pass ``record()`` may read today.
#: Shrink-only ratchet — see module docstring.
_PINNED_WIDGET_READS = {
    "src/tabs/image_compare/canvas/features/capture/passes.py": [
        "widget.renderTarget",
    ],
    "src/tabs/image_compare/canvas/features/divider/passes.py": [
        "widget.renderTarget",
    ],
    "src/tabs/image_compare/canvas/features/drag_drop_overlay/passes.py": [],
    "src/tabs/image_compare/canvas/features/filename_overlay/passes.py": [
        # One DPR resolution: the viewport is the render target's own
        # pixelSize() like the six siblings. The ratio read stays because it is
        # the named device-px fallback for a host with no mountable target.
        "widget.devicePixelRatioF",
        "widget.renderTarget",
    ],
    "src/tabs/image_compare/canvas/features/guides/passes.py": [
        "widget.renderTarget",
        "widget.runtime_state",
        "widget.runtime_state._clip_overlays_to_content_rect",
    ],
    "src/tabs/image_compare/canvas/features/magnifier/render/arc_passes.py": [
        "widget.renderTarget",
        "widget.runtime_state",
    ],
    "src/tabs/image_compare/canvas/features/magnifier/render/magnifier_pass.py": [
        "widget.renderTarget",
        "widget.runtime_state",
    ],
    # R3b: both canvas/rhi_overlay_pass_base.py mirrors retired (their
    # record() moved into the mounted passes + engine shell) -- entries
    # removed deliberately, not by accident.
    "src/tabs/multi_compare/canvas/features/drag_drop_overlay/passes.py": [
        "widget.state",
    ],
    # R3b: labels + focus_dim define their own record() for the first time
    # (they mount TexturedOverlayShell directly after the mirror retire;
    # previously they inherited record() from the mirror base). Both are
    # ctx-only (framebuffer size from ctx, draw through the shell) -- they
    # join the pin at zero, the target state for mounted passes.
    "src/tabs/multi_compare/canvas/features/focus_dim/passes.py": [],
    "src/tabs/multi_compare/canvas/features/layer_labels/passes.py": [],
    "src/tabs/multi_compare/canvas/features/grid_dividers/passes.py": [],
    "src/tabs/multi_compare/scene/passes/base_images.py": [],
}


def _record_functions(path):
    """Every ``def record(...)`` in a file with its arg names and node."""
    tree = parse(path)
    if tree is None:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "record":
            out.append(
                (
                    node,
                    [a.arg for a in node.args.args]
                    + [a.arg for a in node.args.kwonlyargs],
                )
            )
    return out


def _pass_files() -> list:
    """Tab files defining a pass ``record()`` (bus itself excluded)."""
    found = []
    for py in iter_py(TABS):
        if rel(py) in _EXCLUDED_FILES:
            continue
        if _record_functions(py):
            found.append(py)
    return sorted(found)


def _dotted_chain(node: ast.Attribute) -> tuple[str, ...] | None:
    """Full ``a.b.c`` chain for an Attribute, or None if not name-rooted."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return tuple(reversed(parts))


def _widget_chains(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    chains: set[str] = set()
    for node in ast.walk(func):
        if not isinstance(node, ast.Attribute):
            continue
        chain = _dotted_chain(node)
        if chain is not None and chain[0] == "widget":
            chains.add(".".join(chain))
    return sorted(chains)


def _store_reads(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Attribute):
            continue
        chain = _dotted_chain(node)
        if chain is None:
            continue
        if chain[0] == "store" or (
            chain[0] == "self" and len(chain) > 1 and "store" in chain[1].lower()
        ):
            hits.append(".".join(chain))
    return sorted(set(hits))


def _export_mode_branches(func: ast.FunctionDef | ast.AsyncFunctionDef, text: str) -> list[str]:
    """``mode``-vs-``"export"`` comparisons (any comparator) in a body."""
    hits: list[str] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        names: set[str] = set()
        lits: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                lits.add(child.value)
        if "mode" in names and "export" in lits:
            seg = (ast.get_source_segment(text, node) or "").strip().splitlines()
            hits.append(seg[0][:100] if seg else f"line {node.lineno}")
    return hits


def test_pass_record_methods_take_ctx():
    offenders: list[str] = []
    for py in _pass_files():
        for func, argnames in _record_functions(py):
            if "ctx" not in argnames:
                offenders.append(
                    f"{rel(py)}:{func.lineno} record() has no 'ctx' parameter "
                    f"(args={argnames}) — passes read their context argument"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_pass_record_reads_no_store():
    offenders: list[str] = []
    for py in _pass_files():
        for func, _ in _record_functions(py):
            for hit in _store_reads(func):
                offenders.append(
                    f"{rel(py)}:{func.lineno} record() reads '{hit}' — "
                    f"passes read only their ctx argument, never store state"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_no_export_mode_branch_in_pass_record():
    offenders: list[str] = []
    for py in _pass_files():
        text = py.read_text(encoding="utf-8")
        for func, _ in _record_functions(py):
            for hit in _export_mode_branches(func, text):
                offenders.append(
                    f"{rel(py)}:{func.lineno} record() branches on export mode "
                    f"({hit!r}) — live/snapshot parity is snapshot-replay, "
                    f"never `if mode == \"export\"` in a pass"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_pass_record_widget_reads_are_pinned():
    offenders: list[str] = []
    for py in _pass_files():
        key = rel(py)
        for func, _ in _record_functions(py):
            actual = _widget_chains(func)
            if key not in _PINNED_WIDGET_READS:
                if actual:
                    offenders.append(
                        f"{key}:{func.lineno} new pass record() reads {actual} — "
                        f"new passes must read only ctx (no widget.*); "
                        f"grandfather deliberately via _PINNED_WIDGET_READS"
                    )
                continue
            expected = _PINNED_WIDGET_READS[key]
            if actual != expected:
                offenders.append(
                    f"{key}:{func.lineno} widget reads drifted:\n"
                    f"    expected: {expected}\n"
                    f"    actual:   {actual}\n"
                    f"    (shrink the pin deliberately, never grow it silently)"
                )
    assert not offenders, "\n  - " + "\n  - ".join(offenders)


def test_pinned_widget_reads_are_current():
    actual = {rel(py) for py in _pass_files()}
    expected = set(_PINNED_WIDGET_READS)
    assert actual == expected, (
        "pass-record set drifted:\n"
        f"  added: {sorted(actual - expected)}\n"
        f"  removed: {sorted(expected - actual)}\n"
        "a new pass record() must prove ctx-only reads before joining; "
        "a removed one leaves the pin behind"
    )


# ---------------------------------------------------------------------------
# Frame-bus helpers (bucket 2C deliverable): frame_id, viewport-hash,
# budget stats, ids schema. Runtime pin that the bus surface exists and
# behaves — the AST dogma above guards the readers, this guards the bus.
# ---------------------------------------------------------------------------


def _bus():
    """Load the frame-bus module without importing the tab package.

    ``engine/frame/context.py`` is a stdlib-only leaf (``dataclasses`` +
    ``hashlib``); loading it by file location keeps this host-level
    contract decoupled from ``tabs.*`` package imports (see
    ``test_root_tests_no_tab_internals_leak``) and immune to tab
    ``__init__`` side effects. The AST dogma above already references
    tab paths as scanned data, never as imports.
    """
    import importlib.util
    import sys

    path = (
        ROOT
        / "src"
        / "engine"
        / "frame"
        / "context.py"
    )
    spec = importlib.util.spec_from_file_location(
        "frame_context_bus_contract", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # slots=True dataclasses resolve string annotations via sys.modules.
    sys.modules["frame_context_bus_contract"] = module
    try:
        spec.loader.exec_module(module)
    finally:
        del sys.modules["frame_context_bus_contract"]
    return module


def test_bus_frame_id_advances_per_reset():
    fc = _bus()
    ctx = fc.FrameContext()
    assert ctx.frame_id == 0
    ctx.reset()
    assert ctx.frame_id == 1
    ctx.record("fallback", "ran", "fallback atomic=False")
    ctx.reset()
    assert ctx.frame_id == 2
    assert len(ctx) == 0
    assert ctx.begin_frame() == 3


def test_bus_viewport_hash_stable_and_sensitive():
    fc = _bus()
    base = fc.viewport_hash((1.0, 1.0), (0.0, 0.0))
    assert base == fc.viewport_hash((1.0, 1.0), (0.0, 0.0))
    assert len(base) == 12
    assert fc.viewport_hash((2.0, 2.0), (0.0, 0.0)) != base
    assert fc.viewport_hash((1.0, 1.0), (5.0, 0.0)) != base
    assert fc.viewport_hash(None, None) == fc.viewport_hash(None, None)


def test_bus_budget_stats_shape():
    fc = _bus()
    stats = fc.BudgetStats(
        budget=64, uploaded=60, skipped=4, time_ms=3.5, budget_ms=12.0,
        more_pending=True,
    )
    text = stats.describe()
    assert "budget=64" in text and "uploaded=60" in text
    assert "more_pending=True" in text
    atom = stats.as_tuple()
    assert atom == (64, 60, 4, 3.5, 12.0, True)


def test_bus_ids_schema_leads_with_frame_tag():
    fc = _bus()
    assert fc.IDS_SCHEMA_VERSION == 1
    assert fc.frame_tag(7) == "frame=7"
    ids = fc.make_ids(7, ("stored_0", "stored_1"), None)
    assert ids == ("frame=7", ("stored_0", "stored_1"), None)
    ctx = fc.FrameContext()
    for _ in range(3):
        ctx.reset()
    decision = ctx.record("submit", "ran", "submit entries=4", ids=fc.make_ids(ctx.frame_id, 4))
    assert decision.ids[0] == f"frame={ctx.frame_id}"
