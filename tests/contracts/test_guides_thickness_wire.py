"""Structural half: the guides *thickness* control reaches the painted width.

Owner report (2026-10-26): "толщина лазеров у лупы всегда либо ноль, либо
единица" -- the magnifier guide lines never thickened. It was a severed wire,
not a scale mapping: the toolbar value reached
``runtime_state._guides_thickness`` through ``set_guides_params`` and no
renderer read it, while ``resolve_guide_spans`` painted
``ctx.resolved_style.annotation_line_stroke_px`` (the theme stroke) -- so every
value 1..10 produced the same hairline.

``tests/contracts`` is the host-level suite and may not deep-import a tab's
internals (``test_root_tests_no_tab_internals_leak``), so this file only reads
source; the behavioural assertions (two fixtures differing only in thickness
produce different widths, pass hands the resolved width to the uniform, live
and export producers both carry the slot) live in
``src/tabs/image_compare/tests/render/test_guides_thickness_wire.py``.

Red before the fix: neither producer appended a thickness slot and the
resolver's width was the style px alone, so both scans below failed.
"""

from __future__ import annotations

import ast

from ._framework import SRC, parse

GUIDES = SRC / "tabs" / "image_compare" / "canvas" / "features" / "guides"
OVERLAY_MODEL = GUIDES / "overlay_model.py"
LIVE_PRODUCER = GUIDES / "feature.py"
EXPORT_PRODUCER = (
    SRC
    / "tabs"
    / "image_compare"
    / "canvas"
    / "features"
    / "magnifier"
    / "render"
    / "plan_overlay.py"
)


def _function_source(path, name: str) -> str:
    """Source text of the first ``def name`` in ``path`` (AST segment)."""
    tree = parse(path)
    assert tree is not None, f"cannot parse {path}"
    source = path.read_text(encoding="utf-8")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
            node.name == name
        ):
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"{name} not found in {path}")


def test_resolver_scales_the_theme_stroke_by_the_guide_set_thickness():
    source = _function_source(OVERLAY_MODEL, "resolve_guide_spans")
    # the theme stroke is the floor/base ...
    assert "annotation_line_stroke_px" in source
    # ... and the per-set thickness multiplies it (never a bare style px).
    assert "_guide_set_thickness" in source, (
        "resolve_guide_spans must read the guide set's thickness slot"
    )
    assert "style_px *" in source, (
        "painted line width must scale with thickness, not be the style alone"
    )
    # legacy 5-tuples must not silently paint the floor: the widget-level
    # field the toolbar already fills is the fallback.
    assert "_guides_thickness" in source


def test_resolver_slot_helper_tolerates_legacy_five_tuples():
    source = _function_source(OVERLAY_MODEL, "_guide_set_thickness")
    assert "len(guide_set)" in source and "fallback" in source


def test_both_guide_set_producers_carry_the_thickness_slot():
    """Live (scene apply) and export (plan apply) must emit the same 6-tuple."""
    for path, function in (
        (LIVE_PRODUCER, "apply_guides_object"),
        (EXPORT_PRODUCER, "apply_magnifier_plan_overlay"),
    ):
        source = _function_source(path, function)
        assert "_guide_sets" in source or "converted_guides" in source, (
            f"{path.name}:{function} must still build the guide sets"
        )
        assert "thickness" in source, (
            f"{path.name}:{function} drops the thickness slot, so live and "
            "export disagree about the painted width"
        )


def test_scene_object_and_widget_state_still_expose_the_thickness():
    """The wire's upper half: scene object field + widget state field."""
    objects = (GUIDES / "scene" / "objects.py").read_text(encoding="utf-8")
    assert "thickness" in objects
    state = GUIDES / "state" / "feature_state.py"
    assert "thickness" in state.read_text(encoding="utf-8")
