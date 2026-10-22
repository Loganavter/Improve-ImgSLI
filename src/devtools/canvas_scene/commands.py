"""The mutating half of the canvas scene channel: scene commands (S2).

``get_canvas_scene`` (S1) answers *where* the scene is; this module moves it.
Every command here is **value-taking** (an absolute target, never a toggle) and
routes through the feature's *existing* command/state path — the canvas feature
registry (``viewport.set_instance_visibility``, ``divider.viewport.set_thickness``)
or the tab's own Redux dispatch (``multi_compare/set_split_weights``). Nothing in
this module assigns to Store / view state: the double truth of a scene command
and a direct patch is exactly what S2 exists to prevent.

Tab-aware on purpose, by the same rule as the rest of ``devtools.canvas_scene``:
the host-neutral runner (``core.control.scene_commands``) owns schemas, ordering
and verification and must stay free of tab vocabulary (platform isolation
dogma), so the implementations that name a feature/tab live here.

Each entry of :data:`SCENE_COMMANDS` declares

* ``canvas``  — which scene source it applies to ("ic_scene"/"mc_projection"),
  so a command aimed at the wrong tab is refused instead of half-applied;
* ``params``  — the typed parameter schema; ``core.control.scene_commands``
  refuses unknown keys / wrong types with this schema in the error hint;
* ``scope``   — the scene subtrees the command is *allowed* to change. The
  verifier fails a command that changed anything outside ``expect`` + scope
  ("it ran" is not "it happened", and a command that silently moved something
  else did not happen either). Placeholders (``{id}``) read the command params.
* ``apply``   — ``(canvas, params, *, tab) -> None``; raises ``MethodError`` when
  the target does not exist or the canvas cannot run commands.
"""

from __future__ import annotations

from typing import Any, Callable

from .common import _stored_canvas_widget_state

#: Scene sources (mirror ``serialize_canvas``) — a command names the one it fits.
IC_SCENE = "ic_scene"
MC_PROJECTION = "mc_projection"


def canvas_scene_source(canvas: Any) -> str | None:
    """Which scene source this canvas speaks (``None``: not a scene canvas)."""
    from . import _is_ic_canvas, _is_mc_canvas

    if _is_mc_canvas(canvas):
        return MC_PROJECTION
    if _is_ic_canvas(canvas):
        return IC_SCENE
    return None


# ---------------------------------------------------------------------------
# Image Compare: magnifier instances + the split divider
# ---------------------------------------------------------------------------


def _method_error(message: str, hint: str | None = None) -> Exception:
    """``MethodError`` resolved lazily (devtools must not import the channel)."""
    from core.control.discovery import MethodError

    return MethodError(message, hint)


def _ic_store(canvas: Any) -> Any:
    from .image_compare import _ic_store as resolve

    return resolve(canvas, getattr(canvas, "runtime_state", None))


def _ic_view_state(canvas: Any) -> Any:
    store = _ic_store(canvas)
    viewport = getattr(store, "viewport", None)
    return getattr(viewport, "view_state", None)


def _ic_command(tab: str, command_id: str, *, alias: bool) -> Callable[..., Any]:
    """One command from the tab's canvas feature registry (never a state write).

    ``command_id`` is either a capability alias (``overlay.set_instance_visibility``,
    ``alias=True``) or ``<feature>:<command id>`` (``divider:viewport.set_thickness``)
    — both are the registry's own vocabulary, so no command is re-implemented here.
    """
    from ui.canvas_infra.scene.registry import get_canvas_registry

    registry = get_canvas_registry(tab)
    command = (
        registry.get_feature_command_by_alias(command_id)
        if alias
        else registry.get_feature_command(*command_id.split(":", 1))
    )
    if not callable(command):
        raise _method_error(
            f"the canvas feature command {command_id!r} is not registered for tab {tab!r}",
            "open that tab once so its canvas features register, then retry "
            "(get_canvas_scene names the scene source it found)",
        )
    return command


def _magnifier_models(canvas: Any) -> dict[str, Any]:
    state, _materialized = _stored_canvas_widget_state(_ic_view_state(canvas), "magnifier")
    return dict(getattr(state, "models", None) or {})


def _require_magnifier(canvas: Any, magnifier_id: Any) -> str:
    """The instance id, or ``MethodError`` naming the ones that do exist."""
    models = _magnifier_models(canvas)
    known = sorted(models)
    target = str(magnifier_id)
    if target not in models:
        hint = (
            "known instances: " + ", ".join(known)
            if known
            else "this scene has no magnifier instances yet — add one with the "
            "magnifier toolbar (list_actions: magnifier.* actions)"
        )
        raise _method_error(f"no magnifier instance {target!r}", hint)
    return target


def _ic_select(canvas: Any, tab: str, magnifier_id: str) -> None:
    """Make *magnifier_id* the active instance (the per-instance setters act on it).

    Declared side effect: the scene's ``active`` marker moves too, which is why
    the magnifier commands' scope is the whole ``magnifiers`` subtree.
    """
    _ic_command(tab, "overlay.set_active_instance", alias=True)(
        _ic_store(canvas), magnifier_id
    )


def _ic_scene_graph(canvas: Any, tab: str) -> Any:
    """The canvas' usable cached scene graph, or ``None`` when there is none.

    Through the feature's capability alias — devtools must not import a canvas
    feature directly (``tests/contracts/test_canvas_features_imports.py``: "use
    capability aliases").
    """
    return _ic_command(tab, "overlay.scene_graph", alias=True)(
        _ic_store(canvas), canvas
    )


def _ic_refresh_scene_graph(canvas: Any, tab: str) -> None:
    """Rebuild the cached magnifier objects from the current state (alias)."""
    _ic_command(tab, "overlay.refresh_scene_graph", alias=True)(
        _ic_store(canvas), canvas
    )


def _ic_set_magnifier_visible(canvas: Any, params: dict[str, Any], *, tab: str) -> None:
    magnifier_id = _require_magnifier(canvas, params["id"])
    _ic_command(tab, "overlay.set_instance_visibility", alias=True)(
        _ic_store(canvas), magnifier_id, bool(params["visible"])
    )


def _ic_set_magnifier_position(canvas: Any, params: dict[str, Any], *, tab: str) -> None:
    from domain.types import Point

    magnifier_id = _require_magnifier(canvas, params["id"])
    _ic_select(canvas, tab, magnifier_id)
    _ic_command(tab, "overlay.move_active_position", alias=True)(
        _ic_store(canvas), Point(float(params["x"]), float(params["y"]))
    )


def _ic_set_magnifier_size(canvas: Any, params: dict[str, Any], *, tab: str) -> None:
    magnifier_id = _require_magnifier(canvas, params["id"])
    _ic_select(canvas, tab, magnifier_id)
    _ic_command(tab, "overlay.set_active_size", alias=True)(
        _ic_store(canvas), float(params["size"])
    )


def _ic_set_magnifier_combined(canvas: Any, params: dict[str, Any], *, tab: str) -> None:
    """Set the instance's combined mode and refresh the scene graph it is read from.

    ``is_combined`` is not a stored field: the scene derives it from
    ``visible_left and visible_right and spacing == 0``. So the write is the
    spacing command (``overlay.set_active_combined``, which owns the 0.0 ↔
    default-spacing decision) and the *read* is a scene-graph refresh — without
    it ``expect: magnifiers[i].is_combined`` would compare against the previous
    frame's cache and fail for a command that actually worked.

    Preconditions are refused *before* the write, with the reason: a hidden
    instance reports ``is_combined: null`` (no scene-graph geometry), and a
    loupe with one side hidden can never be combined — both would turn
    "unverifiable" into a state change nobody can see.
    """
    magnifier_id = _require_magnifier(canvas, params["id"])
    model = _magnifier_models(canvas)[magnifier_id]
    if not bool(getattr(model, "visible", False)):
        raise _method_error(
            f"magnifier {magnifier_id!r} is hidden, so its combined mode has no "
            "scene geometry to report",
            "make the instance visible first (magnifier.set_visible with "
            "visible: true), then set its combined mode — get_canvas_scene "
            "reports is_combined: null for a hidden instance",
        )
    combined = bool(params["combined"])
    if combined and not (
        bool(getattr(model, "visible_left", False))
        and bool(getattr(model, "visible_right", False))
    ):
        raise _method_error(
            f"magnifier {magnifier_id!r} cannot be combined: both sides must be "
            f"visible (left={bool(getattr(model, 'visible_left', False))}, "
            f"right={bool(getattr(model, 'visible_right', False))})",
            "is_combined is derived from visible_left + visible_right + spacing 0; "
            "enable the hidden side (left/right visibility) in the magnifier "
            "toolbar, then retry",
        )
    if _ic_scene_graph(canvas, tab) is None:
        raise _method_error(
            "this canvas has no scene graph yet, so the combined mode cannot be "
            "verified in this call",
            "let the tab paint one frame (open it with open_tab, then re-read "
            "with get_canvas_scene) and retry",
        )

    _ic_select(canvas, tab, magnifier_id)
    _ic_command(tab, "overlay.set_active_combined", alias=True)(
        _ic_store(canvas), combined
    )
    _ic_refresh_scene_graph(canvas, tab)


def _ic_set_divider_visible(canvas: Any, params: dict[str, Any], *, tab: str) -> None:
    _ic_command(tab, "divider:viewport.toggle_visibility", alias=False)(
        _ic_store(canvas), bool(params["visible"])
    )


def _ic_set_divider_thickness(canvas: Any, params: dict[str, Any], *, tab: str) -> None:
    _ic_command(tab, "divider:viewport.set_thickness", alias=False)(
        _ic_store(canvas), int(params["thickness"])
    )


# ---------------------------------------------------------------------------
# Multi Compare: the split tree
# ---------------------------------------------------------------------------


def _mc_dispatch(canvas: Any) -> tuple[Callable[[Any], Any], Any]:
    """The tab's own dispatch callable + the store behind it (no state writes)."""
    dispatch = getattr(canvas, "_dispatch", None)
    if not callable(dispatch):
        raise _method_error(
            "this Multi Compare canvas has no dispatch installed",
            "the command path is the tab's Redux dispatch; a canvas built outside "
            "the tab (a bare widget in a test) must call set_dispatch(store.dispatch) first",
        )
    store = getattr(dispatch, "__self__", None)
    state = getattr(store, "state", None)
    if state is None:
        state = getattr(canvas, "state", None)
    return dispatch, state


def _mc_settle(canvas: Any) -> None:
    """Push the dispatched state into the canvas and rebuild its composition.

    A production canvas rebuilds on the coalesced flush after the store
    notification; a *verified* command cannot wait a tick, and a background/
    offscreen canvas defers the flush entirely — so the scene read that follows
    must see the composition the dispatch produced, not the previous frame.
    Both calls are the canvas' own public/documented seams (``set_state`` is
    what the tab's ``_on_store_change`` calls; ``_rebuild_composition`` is the
    body of its deferred flush) — no state is written here.
    """
    dispatch, state = _mc_dispatch(canvas)
    if state is not None and callable(getattr(canvas, "set_state", None)):
        canvas.set_state(state)
    rebuild = getattr(canvas, "_rebuild_composition", None)
    if callable(rebuild):
        rebuild()


def _mc_set_split_weights(canvas: Any, params: dict[str, Any], *, tab: str) -> None:
    from tabs.multi_compare.models import SplitNode, node_at_path
    from tabs.multi_compare.scene import actions as mc_actions

    path = tuple(int(step) for step in params["path"])
    weights = [float(weight) for weight in params["weights"]]
    dispatch, state = _mc_dispatch(canvas)
    node = node_at_path(getattr(state, "root", None), path)
    if not isinstance(node, SplitNode):
        raise _method_error(
            f"no split node at path {list(path)}",
            "path is the chain of child indices from the root to a SplitNode "
            "(root = []); call get_canvas_scene to see the panes the current tree renders",
        )
    if len(weights) != len(node.children):
        raise _method_error(
            f"the split at path {list(path)} has {len(node.children)} children, "
            f"so it takes {len(node.children)} weights, got {len(weights)}",
            "weights are one per child in that split, left/top first",
        )
    dispatch(mc_actions.set_split_weights(path, weights))
    _mc_settle(canvas)


# ---------------------------------------------------------------------------
# the table (schema + scope + implementation, one home per command)
# ---------------------------------------------------------------------------

_INSTANCE_PARAM = {
    "type": "str",
    "required": True,
    "description": "Magnifier instance id, exactly as get_canvas_scene lists it.",
}

SCENE_COMMANDS: dict[str, dict[str, Any]] = {
    "magnifier.set_visible": {
        "canvas": IC_SCENE,
        "summary": "set one magnifier instance's visible flag (absolute value, not a toggle)",
        "params": {
            "id": _INSTANCE_PARAM,
            "visible": {
                "type": "bool",
                "required": True,
                "description": "true paints the instance, false hides it (a hidden instance keeps its state).",
            },
        },
        "example": {"id": "loupe-a", "visible": False},
        "scope": ("magnifiers", "render_layout", "sources", "unavailable"),
        "apply": _ic_set_magnifier_visible,
    },
    "magnifier.set_position": {
        "canvas": IC_SCENE,
        "summary": (
            "move one magnifier instance's center (relative 0..1 canvas "
            "coordinates); it also becomes the active instance"
        ),
        "params": {
            "id": _INSTANCE_PARAM,
            "x": {
                "type": "float",
                "required": True,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Horizontal center as a fraction of the canvas width (0 = left edge).",
            },
            "y": {
                "type": "float",
                "required": True,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Vertical center as a fraction of the canvas height (0 = top edge).",
            },
        },
        "example": {"id": "loupe-a", "x": 0.3, "y": 0.6},
        "scope": ("magnifiers", "render_layout", "sources", "unavailable"),
        "apply": _ic_set_magnifier_position,
    },
    "magnifier.set_size": {
        "canvas": IC_SCENE,
        "summary": (
            "set one magnifier instance's radius (relative to the canvas short "
            "side); it also becomes the active instance"
        ),
        "params": {
            "id": _INSTANCE_PARAM,
            "size": {
                "type": "float",
                "required": True,
                "minimum": 0.01,
                "maximum": 1.0,
                "description": "Radius as a fraction of the canvas' short side (the app default is 0.2).",
            },
        },
        "example": {"id": "loupe-a", "size": 0.3},
        "scope": ("magnifiers", "render_layout", "sources", "unavailable"),
        "apply": _ic_set_magnifier_size,
    },
    "magnifier.set_combined": {
        "canvas": IC_SCENE,
        "summary": (
            "set one magnifier instance's combined mode (both sides folded into "
            "one loupe at zero spacing); it also becomes the active instance"
        ),
        "params": {
            "id": _INSTANCE_PARAM,
            "combined": {
                "type": "bool",
                "required": True,
                "description": (
                    "true folds the two sides into one combined loupe (spacing "
                    "0.0); false splits them again at the app's default spacing. "
                    "Both sides must be visible, and a hidden instance reports "
                    "is_combined: null."
                ),
            },
        },
        "example": {"id": "loupe-a", "combined": True},
        "scope": ("magnifiers", "render_layout", "sources", "unavailable"),
        "apply": _ic_set_magnifier_combined,
    },
    "divider.set_visible": {
        "canvas": IC_SCENE,
        "summary": "show or hide the split divider of the image pair",
        "params": {
            "visible": {
                "type": "bool",
                "required": True,
                "description": "true paints the split line, false suppresses it.",
            }
        },
        "example": {"visible": False},
        "scope": ("dividers", "sources", "unavailable"),
        "apply": _ic_set_divider_visible,
    },
    "divider.set_thickness": {
        "canvas": IC_SCENE,
        "summary": "set the split divider width (widget px; 0 also hides the line)",
        "params": {
            "thickness": {
                "type": "int",
                "required": True,
                "minimum": 0,
                "maximum": 10,
                "description": "Divider width in widget px (the app clamps 0..10); 0 hides the divider too.",
            }
        },
        "example": {"thickness": 5},
        "scope": ("dividers", "sources", "unavailable"),
        "apply": _ic_set_divider_thickness,
    },
    "layout.set_split_weights": {
        "canvas": MC_PROJECTION,
        "summary": "set one split's child weights (absolute fractions, not a drag delta)",
        "params": {
            "path": {
                "type": "int_list",
                "required": True,
                "description": "Child-index chain from the root to the split (root itself = []).",
            },
            "weights": {
                "type": "float_list",
                "required": True,
                "description": "One weight per child of that split, summing to ~1.0; the tab clamps below 0.15.",
            },
        },
        "example": {"path": [], "weights": [0.5, 0.5]},
        "scope": ("panes", "dividers", "canvas", "transform", "sources", "unavailable"),
        "apply": _mc_set_split_weights,
    },
}


def command_names() -> list[str]:
    """Every scene command id (sorted), for hints and for the tool description."""
    return sorted(SCENE_COMMANDS)
