"""Per-canvas adapters for the ``get_canvas_scene`` read verb.

This module is the tab-aware half of the scene read. It lives under
``devtools`` — like ``app_snapshot`` / ``ui_layout_dump``, it produces a
control-surface artifact from the live window, so naming tab internals here is
the same kind of knowledge those modules already carry. The host-neutral entry
(``core.control.scene_read``) resolves the tab, finds the canvas and frames the
honest answer; it must stay free of tab vocabulary (platform isolation dogma).

Non-negotiables — each one is a regression already paid for (see
``RECON-canvas-scene-s0.md``):

R1 **Two loupe truths.** Image Compare keeps *all* instances (hidden included,
canvas px) in ``runtime_state._canvas_scene_graph``
(``magnifier/workers/scene_update.py:55``) but *paints* from ``OverlayLayout``
(``magnifier/geometry/layout_plan.py:94-100``), which filters
``model.visible``. A hidden loupe therefore has **no canvas geometry in the
render path**: this module reports it as a hidden instance with
``geometry_source: null`` and a reason, never with borrowed coordinates. Every
geometry block names its source; the payload's ``sources`` map repeats it.

R2 **A read must not mutate.** ``get_magnifier_widget_state`` /
``get_divider_widget_state`` / ``get_capture_widget_state`` /
``ensure_zoom_viewport_state`` *create* state on first read. This module only
reads the stored dicts / attributes (``canvas_widget_state[...]``,
``runtime_state._zoom_viewport_state``) and reports the documented defaults
without writing them back (``state_materialized: false``).

R3 **One projection, two pane sets.** The Multi Compare transform is whatever
``tabs.multi_compare.scene.projection.build_render_context`` produces — never a
second geometry implementation. The pane *set* is reported twice on purpose:
panes in the renderer's composition (``composition_builder.py:162-204``) and
panes that only exist for hit-testing (``ui/layout_geometry.py:10-53``), the
latter with the reason they are not painted (focus-collapsed / imageless).

R4 **No implicit coordinate mixing.** Image Compare speaks canvas px, Multi
Compare speaks composition px; every geometry field carries ``space``.

R5 **Determinism.** Rows are sorted and values come from the scene (never from
iteration order), so two reads of one scene are byte-identical once the caller
serializes with sorted keys (``scene_read.canonical_json``).

R6 **Honesty over shape.** A hidden instance is reported *as hidden* with no
geometry; a feature the tab does not have is named in ``unavailable``.

R7 **Roles are per circle.** Roles are ``diff|combined|left|right|center`` per
drawn circle; there is no per-loupe zoom field (magnification is
``radius`` / ``capture radius``). Nothing here invents one.
"""

from __future__ import annotations

from typing import Any

from .common import (
    SPACE_CANVAS_PX,
    SPACE_COMPOSITION_PX,
    SPACE_FRAMEBUFFER_PX,
    SPACE_RELATIVE,
    SPACE_WIDGET_PX,
)
from .image_compare import _image_compare_scene
from .multi_compare import _multi_compare_scene

__all__ = [
    "SPACE_CANVAS_PX",
    "SPACE_COMPOSITION_PX",
    "SPACE_FRAMEBUFFER_PX",
    "SPACE_RELATIVE",
    "SPACE_WIDGET_PX",
    "empty_scene_payload",
    "is_canvas_widget",
    "serialize_canvas",
]


def is_canvas_widget(widget: Any) -> bool:
    """Can this widget's scene be serialized here? (duck-typed capability)"""
    return _is_ic_canvas(widget) or _is_mc_canvas(widget)


def empty_scene_payload(reason: str) -> dict[str, Any]:
    """The honest shape for "there is no scene": named reason, no fake rows.

    A tab without a canvas must not look like a scene with zero panes, so the
    key set stays identical while has_canvas/reason carry the verdict.
    """
    return {
        "space": None,
        "canvas": None,
        "panes": [],
        "dividers": [],
        "magnifiers": [],
        "transform": None,
        "render_layout": None,
        "focus": None,
        "sources": {},
        "unavailable": [{"field": "scene", "reason": reason}],
    }


def serialize_canvas(canvas: Any) -> dict[str, Any]:
    """Serialize the scene of one live canvas widget (no writes, no rendering)."""
    if _is_mc_canvas(canvas):
        payload = _multi_compare_scene(canvas)
        payload["scene_source"] = "mc_projection"
        payload["space"] = SPACE_COMPOSITION_PX
    else:
        payload = _image_compare_scene(canvas)
        payload["scene_source"] = "ic_scene"
        payload["space"] = SPACE_CANVAS_PX
    payload["unavailable"] = sorted(
        payload.get("unavailable") or [],
        key=lambda row: (str(row.get("field")), str(row.get("reason"))),
    )
    return payload


def _is_ic_canvas(widget: Any) -> bool:
    """Image Compare canvas: a runtime state carrying the scene-graph cache."""
    runtime_state = getattr(widget, "runtime_state", None)
    return runtime_state is not None and hasattr(runtime_state, "_canvas_scene_graph")


def _is_mc_canvas(widget: Any) -> bool:
    """Multi Compare canvas: composition state + resolved composition slot."""
    state = getattr(widget, "state", None)
    return (
        state is not None
        and hasattr(state, "root")
        and hasattr(state, "slots")
        and hasattr(widget, "_active_composition")
    )


