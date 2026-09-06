"""Session (de)serialization, layout-tree (de)serialization, and QSettings
"last used" divider/label persistence for the Multi Compare tab -- split out
of ``tab.py`` to keep that file down to the ``TabContract`` surface itself,
mirroring the ``use_cases`` split applied to image_compare's own
``use_cases/persistence.py``. ``serialize_session``/``deserialize_session``/
``collect_pixel_cache_sources``/``on_session_created`` are required
``TabContract`` method names (or called directly from one), so ``tab.py``
keeps thin delegators of those exact names; everything else here is private
and only ever called from those delegators.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QSettings

from tabs.contract import TabContext

logger = logging.getLogger("ImproveImgSLI")

_STATE_SLOT = "multi_compare.state"
_QS_ORG = "improve-imgsli"
_QS_APP = "improve-imgsli"
_QS_KEY = "multi_compare/last_session_settings"


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

    if data is None:
        return None
    if data.get("type") == "leaf":
        return LeafNode(slot_id=data["slot_id"])
    return SplitNode(
        direction=data.get("direction", "h"),
        children=[_deserialize_layout_node(c) for c in data.get("children", [])],
        weights=list(data.get("weights", [])),
    )


def _save_last_settings(divider, label) -> None:
    try:
        data = {"divider": _divider_to_dict(divider), "label": _label_to_dict(label)}
        settings = QSettings(_QS_ORG, _QS_APP)
        settings.setValue(_QS_KEY, json.dumps(data))
        settings.sync()
        logger.debug(
            "[mc-divider-persist] save QSettings color=%s thickness=%s file=%s",
            list(divider.color_rgba),
            divider.thickness,
            settings.fileName(),
        )
    except Exception:
        logger.exception("mc: failed to save last session settings")


def _load_last_settings():
    try:
        settings = QSettings(_QS_ORG, _QS_APP)
        raw = settings.value(_QS_KEY)
        if not raw:
            logger.debug(
                "[mc-divider-persist] load QSettings empty key=%s file=%s",
                _QS_KEY,
                settings.fileName(),
            )
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw).decode("utf-8")
        elif not isinstance(raw, str):
            raw = str(raw)
        data = json.loads(raw)
        divider = _divider_from_dict(data.get("divider", {}))
        label = _label_from_dict(data.get("label", {}))
        logger.debug(
            "[mc-divider-persist] load QSettings color=%s thickness=%s",
            list(divider.color_rgba),
            divider.thickness,
        )
        return (divider, label)
    except Exception:
        logger.exception("mc: failed to load last session settings")
        return None


def _settings_from_qsettings():
    """Last-used divider/label from QSettings — seed for every new MC session."""
    loaded = _load_last_settings()
    if loaded is None:
        return None
    from tabs.multi_compare.models import MultiCompareState

    divider, label = loaded
    return MultiCompareState(divider_settings=divider, label_settings=label)


def _settings_from_sibling_session(store, *, exclude: str):
    """Copy divider/label chrome from another live MC session (QSettings fallback)."""
    from dataclasses import replace

    from tabs.multi_compare.models import MultiCompareState

    for session in store.list_workspace_sessions():
        if getattr(session, "session_type", None) != "multi_compare":
            continue
        if session.id == exclude:
            continue
        slot = session.state_slots.get(_STATE_SLOT)
        if slot is None:
            continue
        return replace(
            MultiCompareState(),
            divider_settings=slot.divider_settings,
            label_settings=slot.label_settings,
        )
    return None


def _fresh_default_state():
    from tabs.multi_compare.models import MultiCompareState

    return MultiCompareState()


def _multi_compare_session_count(store) -> int:
    return sum(
        1
        for session in store.list_workspace_sessions()
        if getattr(session, "session_type", None) == "multi_compare"
    )


def on_widget_state_changed(tab, action, state) -> None:
    # Persist "last used" prefs on intentional divider/label edits only.
    # ``replace_state``/session switches must not overwrite QSettings with a
    # transient default. The session slot is written by the core Dispatcher
    # on every MC dispatch — nothing to mirror here.
    action_type = getattr(action, "type", "")
    if action_type in {
        "multi_compare/set_divider_settings",
        "multi_compare/set_label_settings",
    }:
        _save_last_settings(state.divider_settings, state.label_settings)


def on_session_created(tab, session_id: str, context: TabContext) -> None:
    store = getattr(context, "store", None)
    if store is None:
        return
    state = store.ensure_session_state_slot(
        _STATE_SLOT,
        session_id=session_id,
        factory=_fresh_default_state,
    )
    count = _multi_compare_session_count(store)
    seeded = False
    # Every new MC tab inherits last-used divider/label chrome (QSettings).
    # Session slots stay isolated — only the seed is shared, not live state.
    remembered = _settings_from_qsettings()
    if remembered is None and count > 1:
        remembered = _settings_from_sibling_session(store, exclude=session_id)
    if remembered is not None:
        from dataclasses import replace

        state = replace(
            state,
            divider_settings=remembered.divider_settings,
            label_settings=remembered.label_settings,
        )
        store.set_session_state_slot(
            _STATE_SLOT,
            state,
            session_id=session_id,
            emit_scope=None,
        )
        seeded = True
    logger.debug(
        "[mc-divider-persist] on_session_created id=%s count=%s seeded=%s color=%s",
        session_id,
        count,
        seeded,
        list(state.divider_settings.color_rgba),
    )
    # ``create_workspace_session`` emits workspace state *before*
    # WorkspaceSessionCreatedEvent, so the presenter may have activated the
    # tab and re-read defaults already. Push the seeded slot into the live
    # widget if it is already bound.
    if (
        seeded
        and tab._widget is not None
        and (
            tab._active_session_id == session_id
            or tab._resolve_active_session_id(context) == session_id
        )
    ):
        tab._active_session_id = session_id
        tab._widget.refresh_from_session()


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
    return {
        "version": 1,
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
        "max_slots": state.max_slots,
        "label_settings": _label_to_dict(state.label_settings),
        "divider_settings": _divider_to_dict(state.divider_settings),
    }


def collect_pixel_cache_sources(tab, session_id: str, context: TabContext) -> dict:
    """Open pixel stores for this session's slots (project-save embedding).

    B1: slots are path-only — sources resolve from the tab's session pixel
    cache, filtered to this session's live slot paths (per-session contract
    preserved; dormant-session leftovers in the LRU never leak into a save).
    Only open ``TiledPixelStore`` instances are returned (previews are
    re-decodable on reopen).
    """
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

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


def deserialize_session(tab, session_id: str, data: dict, context: TabContext) -> None:
    store = getattr(context, "store", None)
    if store is None or not data:
        return
    from tabs.multi_compare.models import CompareSlot, MultiCompareState

    slots = [
        CompareSlot(
            id=e["id"],
            path=Path(e["path"]) if e.get("path") else None,
            label=e.get("label", ""),
        )
        for e in data.get("slots", [])
    ]
    state = MultiCompareState(
        slots=slots,
        root=_deserialize_layout_node(data.get("root")),
        focused_slot_id=data.get("focused_slot_id"),
        zoom=data.get("zoom", 1.0),
        pan_x=data.get("pan_x", 0.0),
        pan_y=data.get("pan_y", 0.0),
        max_slots=data.get("max_slots", 12),
        label_settings=_label_from_dict(data.get("label_settings") or {}),
        divider_settings=_divider_from_dict(data.get("divider_settings") or {}),
    )
    store.set_session_state_slot(
        _STATE_SLOT, state, session_id=session_id, emit_scope=None,
    )
