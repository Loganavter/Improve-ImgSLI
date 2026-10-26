"""Structural half: the guides *thickness* control reaches the painted width.

Owner report (2026-10-26): "толщина лазеров у лупы всегда либо ноль, либо
единица" -- the magnifier guide lines never thickened. It was a severed wire,
not a scale mapping: the toolbar value reached
``runtime_state._guides_thickness`` through ``set_guides_params`` and no
renderer read it, while ``resolve_guide_spans`` painted
``ctx.resolved_style.annotation_line_stroke_px`` (the theme stroke) -- so every
value 1..10 produced the same hairline.

Follow-up (same day, after #696 landed): the wire existed but the mapping
multiplied the theme stroke by the control value, so thickness 10 painted a
fat band instead of a 10 px line. The value is a WIDTH, in the same unit the
magnifier/table/grid dividers take from their toolbar control
(``divider_thickness_px`` -> the bar width, no theme multiplier); the theme
stroke is only the hairline floor.

``tests/contracts`` is the host-level suite and may not deep-import a tab's
internals (``test_root_tests_no_tab_internals_leak``), so this file only reads
source; the behavioural assertions (two fixtures differing only in thickness
produce the divider-like widths, a thick theme stroke cannot rescale the
control value, pass hands the resolved width to the uniform, live and export
producers both carry the slot) live in
``src/tabs/image_compare/tests/render/test_guides_thickness_wire.py``.

Red before #696: neither producer appended a thickness slot and the
resolver's width was the style px alone, so both scans below failed. Red
before this follow-up: the resolver multiplied (``style_px * thickness``) and
the width-unit assertion below failed.
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


def _line_width_value_node():
    """AST of the ``line_width = ...`` right-hand side in the resolver."""
    source = _function_source(OVERLAY_MODEL, "resolve_guide_spans")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name) and target.id == "line_width"
                for target in node.targets
            ):
                return node.value
    raise AssertionError("resolve_guide_spans no longer assigns line_width")


def _contains(node, predicate) -> bool:
    return any(predicate(child) for child in ast.walk(node))


def test_resolver_width_is_the_control_value_floored_by_the_theme_stroke():
    """The thickness slot is a WIDTH, like the divider -- not a multiplier.

    Sibling convention (measured): the magnifier divider takes the toolbar
    value as ``divider_thickness_px`` and paints it as the bar's px width
    (``plan_builder.py``), the table/grid dividers the same way; the theme
    stroke (``tokens.guides_stroke_du`` -> ``resolve_view_px``) is a hairline
    floor. So the resolver must be ``max(style_px, thickness)``.
    """
    source = _function_source(OVERLAY_MODEL, "resolve_guide_spans")
    # the theme stroke is the floor ...
    assert "annotation_line_stroke_px" in source
    # ... and the per-set thickness is the WIDTH (never a bare style px).
    assert "_guide_set_thickness" in source, (
        "resolve_guide_spans must read the guide set's thickness slot"
    )
    # legacy 5-tuples must not silently paint the floor: the widget-level
    # field the toolbar already fills is the fallback.
    assert "_guides_thickness" in source
    # The old #696 rule multiplied the theme stroke by the control value and
    # painted a fat band instead of a line (owner report 2026-10-26).
    assert "style_px *" not in source, (
        "the control value is a width in px, not a multiplier on the theme "
        "stroke -- see the divider's divider_thickness_px"
    )
    width = _line_width_value_node()
    assert isinstance(width, ast.Call) and isinstance(width.func, ast.Name), (
        "line_width must be a plain call expression"
    )
    assert width.func.id == "max", (
        "line_width must be max(theme floor, control width), got "
        f"{width.func.id}()"
    )
    assert _contains(
        width, lambda n: isinstance(n, ast.Name) and n.id == "style_px"
    ), "the theme stroke must stay the floor of the width"
    assert _contains(
        width,
        lambda n: isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_guide_set_thickness",
    ), "the width must come from the guide set's thickness slot"


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
