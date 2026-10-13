"""Session (de)serialization, layout-tree (de)serialization, and the divider/label
chrome codec for the Multi Compare tab -- split out of ``tab.py`` to keep that
file down to the ``TabContract`` surface itself, mirroring the ``use_cases``
split applied to image_compare's own ``use_cases/persistence.py``.
``serialize_session``/``deserialize_session``/
``collect_pixel_cache_sources``/``on_session_created`` are required
``TabContract`` method names (or called directly from one), so ``tab.py``
keeps thin delegators of those exact names; everything else here is private
and only ever called from those delegators. Divider/label chrome (last-used
QSettings, new-session seed, project I/O) goes through the ``SessionState``
facade, bound to ``_STATE_SLOT`` with ``chrome_extract``/``chrome_merge``.
Audit-Meta: pattern=thin-owner-target reason="TabContract session/restore surface: serialize/deserialize/rehydrate plus entry validation share one module beside the models they validate"
"""

from __future__ import annotations

import logging
from pathlib import Path

from tabs.contract import TabContext
from tabs.multi_compare.models import (
    MultiCompareDividerSettings,
    MultiCompareLabelSettings,
)

logger = logging.getLogger("ImproveImgSLI")

_STATE_SLOT = "multi_compare.state"
_LAST_USED_KEY = "multi_compare/last_session_settings"


def _divider_to_dict(divider) -> dict:
    return {
        "visible": divider.visible,
        "thickness": divider.thickness,
        "color_rgba": list(divider.color_rgba),
    }


def _divider_from_dict(d: dict):
    from tabs.multi_compare.models import (
        DEFAULT_DIVIDER_COLOR_RGBA,
        MultiCompareDividerSettings,
    )

    raw = d.get("color_rgba")
    if (
        isinstance(raw, (list, tuple))
        and len(raw) == 4
        and all(isinstance(v, (int, float)) for v in raw)
        and int(raw[3]) > 0
    ):
        color_rgba = (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
    else:
        color_rgba = DEFAULT_DIVIDER_COLOR_RGBA
    return MultiCompareDividerSettings(
        visible=d.get("visible", True),
        thickness=d.get("thickness", 4),
        color_rgba=color_rgba,
    )


def _label_to_dict(label) -> dict:
    return {
        "font_size_percent": label.font_size_percent,
        "font_weight": label.font_weight,
        "text_rgba": list(label.text_rgba),
        "bg_rgba": list(label.bg_rgba),
        "draw_background": label.draw_background,
        "text_alpha_percent": label.text_alpha_percent,
    }


def _label_from_dict(l: dict):
    from domain.qt_adapters import ensure_visible_color
    from domain.types import Color
    from tabs.multi_compare.models import MultiCompareLabelSettings

    text_fallback = Color(255, 255, 255, 255)
    bg_fallback = Color(0, 0, 0, 255)
    text = ensure_visible_color(l.get("text_rgba"), fallback=text_fallback)
    bg = ensure_visible_color(l.get("bg_rgba"), fallback=bg_fallback)
    return MultiCompareLabelSettings(
        font_size_percent=l.get("font_size_percent", 100),
        font_weight=l.get("font_weight", 0),
        text_rgba=(text.r, text.g, text.b, text.a),
        bg_rgba=(bg.r, bg.g, bg.b, bg.a),
        draw_background=l.get("draw_background", True),
        text_alpha_percent=l.get("text_alpha_percent", 100),
    )


def _serialize_layout_node(node) -> dict | None:
    from tabs.multi_compare.models import LeafNode

    if node is None:
        return None
    if isinstance(node, LeafNode):
        return {"type": "leaf", "slot_id": node.slot_id}
    return {
        "type": "split",
        "direction": node.direction,
        "weights": list(node.weights),
        "children": [_serialize_layout_node(c) for c in node.children],
    }


def _deserialize_layout_node(data: dict | None):
    from tabs.multi_compare.models import LeafNode, SplitNode

    if data is None or not isinstance(data, dict):
        return None
    if data.get("type") == "leaf":
        try:
            slot_id = data["slot_id"]
            if isinstance(slot_id, bool) or not isinstance(slot_id, int):
                return None
            return LeafNode(slot_id=slot_id)
        except Exception:
            logger.warning("mc: deserialize_session skipping malformed leaf %r", data)
            return None
    try:
        children_raw = data.get("children", [])
        if not isinstance(children_raw, (list, tuple)):
            children_raw = []
        children = [_deserialize_layout_node(c) for c in children_raw]
        children = [c for c in children if c is not None]
        weights_raw = data.get("weights", [])
        weights = list(weights_raw) if isinstance(weights_raw, (list, tuple)) else []
        return SplitNode(
            direction=data.get("direction", "h"),
            children=children,
            weights=weights,
        )
    except Exception:
        logger.warning("mc: deserialize_session skipping malformed split %r", data)
        return None


def _chrome_as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def chrome_extract(state) -> dict:
    """Typed slot -> SessionState values (``divider``/``label`` dicts)."""
    return {
        "divider": _divider_to_dict(state.divider_settings),
        "label": _label_to_dict(state.label_settings),
    }


def chrome_merge(state, values: dict):
    """SessionState values -> typed slot; pure, partial ``values`` allowed."""
    from dataclasses import replace

    changes = {}
    if "divider" in values:
        changes["divider_settings"] = _divider_from_dict(_chrome_as_dict(values["divider"]))
    if "label" in values:
        changes["label_settings"] = _label_from_dict(_chrome_as_dict(values["label"]))
    return replace(state, **changes) if changes else state


# Defaults mirror a fresh ``MultiCompareState`` so the facade's "never shares
# the default instance" copy starts from the same chrome as the blueprint.
CHROME_FIELDS = {
    "divider": (dict, _divider_to_dict(MultiCompareDividerSettings())),
    "label": (dict, _label_to_dict(MultiCompareLabelSettings())),
}


def _fresh_default_state():
    from tabs.multi_compare.models import MultiCompareState

    return MultiCompareState()


def on_widget_state_changed(tab, action, state) -> None:
    # Persist "last used" prefs on intentional divider/label edits only.
    # ``replace_state``/session switches must not overwrite QSettings with a
    # transient default. The session slot is written by the core Dispatcher
    # on every MC dispatch — the facade only remembers the last-used copy.
    action_type = getattr(action, "type", "")
    if action_type in {
        "multi_compare/set_divider_settings",
        "multi_compare/set_label_settings",
    }:
        tab._session_state.remember(chrome_extract(state))


def on_session_created(tab, session_id: str, context: TabContext) -> None:
    store = getattr(context, "store", None)
    if store is None:
        return
    store.ensure_session_state_slot(
        _STATE_SLOT,
        session_id=session_id,
        factory=_fresh_default_state,
    )
    # Every new MC tab inherits last-used divider/label chrome. Session slots
    # stay isolated — only the seed is shared, not live state.
    tab._session_state.seed_slot(context, session_id)
    # ``create_workspace_session`` emits workspace state *before*
    # WorkspaceSessionCreatedEvent, so the presenter may have activated the
    # tab already; ``seed_slot`` re-applies the seeded slot to the live widget.
    if tab._widget is not None and tab._resolve_active_session_id(context) == session_id:
        tab._active_session_id = session_id


def serialize_session(tab, session_id: str, context: TabContext) -> dict | None:
    store = getattr(context, "store", None)
    if store is None:
        return None
    session = store.get_workspace_session(session_id)
    if session is None or session.session_type != tab.session_type:
        return None
    state = session.state_slots.get(_STATE_SLOT)
    if state is None:
        return None
    chrome = tab._session_state.serialize(context, session_id)
    return {
        "version": _SESSION_VERSION,
        # `image=None` is not persisted — pixel arrays are reloaded from
        # `path` on demand, same rationale as image_compare's ImageItem.
        "slots": [
            {
                "id": s.id,
                "path": str(s.path) if s.path is not None else None,
                "label": s.label,
            }
            for s in state.slots
        ],
        "root": _serialize_layout_node(state.root),
        "focused_slot_id": state.focused_slot_id,
        "zoom": state.zoom,
        "pan_x": state.pan_x,
        "pan_y": state.pan_y,
        # Project keys stay as-is (older builds read them).
        "label_settings": chrome["label"],
        "divider_settings": chrome["divider"],
    }


def collect_pixel_cache_sources(tab, session_id: str, context: TabContext) -> dict:
    """Open pixel stores for this session's slots (project-save embedding).

    B1: slots are path-only — sources resolve from the tab's session pixel
    cache, filtered to this session's live slot paths (per-session contract
    preserved; dormant-session leftovers in the LRU never leak into a save).
    Only open ``TiledPixelStore`` instances are returned (previews are
    re-decodable on reopen).
    """
    from engine.store.tiled_pixel_store import TiledPixelStore

    store = getattr(context, "store", None)
    if store is None:
        return {}
    session = store.get_workspace_session(session_id)
    if session is None or session.session_type != tab.session_type:
        return {}
    state = session.state_slots.get(_STATE_SLOT)
    if state is None:
        return {}
    controller = getattr(tab, "_controller", None)
    cache = getattr(controller, "pixel_cache", None)
    if cache is None:
        return {}
    sources: dict = {}
    for slot in state.slots:
        if slot.path is None:
            continue
        try:
            source = cache.get_pixel(slot.path)
        except Exception:
            continue
        if isinstance(source, TiledPixelStore) and source.is_open:
            sources[str(slot.path)] = source
    return sources


def rehydrate_session(tab, session_id: str, context: TabContext) -> None:
    """Lazy restore (B1): paths are already in the slot — 0 sync decodes.

    P6 ordering (not payload shape): the widget refresh is unconditional
    for the active session — the old ``if not changed: return`` gate
    skipped it exactly when nothing needed decoding, which is the normal
    warm-cache/tab-switch case, leaving a blank canvas. Demand fill is
    kicked for the active session only; dormant sessions fill on
    activation (``tab.on_active_session_changed``).
    """
    store = getattr(context, "store", None)
    if store is None:
        return
    state = store.get_session_state_slot(_STATE_SLOT, session_id=session_id)
    if state is None:
        return

    controller = tab._controller
    if controller is None:
        logger.warning(
            "mc: rehydrate_session skipped — controller unavailable for %s",
            session_id,
        )
        return

    is_active = session_id == tab._active_session_id
    if not is_active:
        try:
            active = store.get_active_workspace_session()
            is_active = active is not None and getattr(active, "id", None) == session_id
        except Exception:
            pass
    if is_active:
        controller.rehydrate_slots(state)

    if is_active and tab._widget is not None:
        tab._widget.refresh_from_session()


_SESSION_VERSION = 1


def _coerce_label(value) -> str:
    try:
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)
    except Exception:
        return ""


def _coerce_number(value, default):
    try:
        number = float(value)
        if number != number:  # NaN guard — never restore NaN zoom/pan
            return default
        return number
    except Exception:
        return default


def _valid_slot_entry(e) -> dict | None:
    """Validate one persisted slot entry — ``None`` means skip-and-log.

    A single malformed entry (missing ``id``, non-int ``id``, non-str
    ``path``) must not abort the whole restore: the caller drops it with a
    warning and keeps the well-formed siblings, so ``project_io``'s
    per-session loop continues past bad sessions instead of dying mid-file.
    """
    if not isinstance(e, dict):
        logger.warning("mc: deserialize_session skipping non-dict slot entry %r", e)
        return None
    slot_id = e.get("id")
    if isinstance(slot_id, bool) or not isinstance(slot_id, int):
        logger.warning("mc: deserialize_session skipping slot entry with bad id %r", e)
        return None
    raw_path = e.get("path")
    if raw_path is not None and not isinstance(raw_path, str):
        logger.warning("mc: deserialize_session skipping slot entry with bad path %r", e)
        return None
    return {
        "id": slot_id,
        "path": Path(raw_path) if raw_path else None,
        "label": _coerce_label(e.get("label", "")),
    }


def _coerce_focused_slot_id(value, slots, root) -> int | None:
    """Validate persisted focus — stale id → ``None`` (focus dropped).

    A corrupt slot entry is skipped without aborting restore, so a saved
    focus id may no longer resolve; seeding it would focus a ghost leaf
    (composition renders nothing while focused). The reducer stays the
    correctness gate (``ApplyLayoutTree``/``RemoveSlot`` drop dead focus);
    this is the fail-fast boundary check on the restore path only, applied
    before seeding the slot.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        logger.warning(
            "mc: deserialize_session dropping non-int focused_slot_id %r", value
        )
        return None
    valid = {s.id for s in slots}
    if root is not None:
        from tabs.multi_compare.models import slot_ids_in_tree

        valid &= slot_ids_in_tree(root)
    if value not in valid:
        logger.warning(
            "mc: deserialize_session dropping stale focused_slot_id %r", value
        )
        return None
    return value


def deserialize_session(tab, session_id: str, data: dict, context: TabContext) -> None:
    store = getattr(context, "store", None)
    if store is None or not data:
        return
    if not isinstance(data, dict):
        logger.warning("mc: deserialize_session skipping non-dict payload %r", data)
        return
    from tabs.multi_compare.models import CompareSlot, MultiCompareState

    try:
        version = data.get("version", _SESSION_VERSION)
    except Exception:
        version = _SESSION_VERSION
    if version != _SESSION_VERSION:
        logger.info(
            "mc: deserialize_session version %r (current %r) — restoring known fields",
            version,
            _SESSION_VERSION,
        )
    slots = []
    for e in data.get("slots", []) or []:
        try:
            valid = _valid_slot_entry(e)
        except Exception:
            logger.warning("mc: deserialize_session skipping unreadable slot entry %r", e)
            continue
        if valid is None:
            continue
        try:
            slots.append(CompareSlot(**valid))
        except Exception:
            logger.warning("mc: deserialize_session skipping unbuildable slot entry %r", e)
            continue
    root = _deserialize_layout_node(data.get("root"))
    state = MultiCompareState(
        slots=slots,
        root=root,
        focused_slot_id=_coerce_focused_slot_id(
            data.get("focused_slot_id"), slots, root
        ),
        zoom=_coerce_number(data.get("zoom", 1.0), 1.0),
        pan_x=_coerce_number(data.get("pan_x", 0.0), 0.0),
        pan_y=_coerce_number(data.get("pan_y", 0.0), 0.0),
    )
    store.set_session_state_slot(
        _STATE_SLOT, state, session_id=session_id, emit_scope=None,
    )
    tab._session_state.deserialize(
        {
            "divider": data.get("divider_settings"),
            "label": data.get("label_settings"),
        },
        context,
        session_id,
    )
