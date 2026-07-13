"""Multi-compare tab contract implementation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QVBoxLayout, QWidget

from tabs.contract import TabContext, TabContract

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
_STATE_SLOT = "multi_compare.state"
_QS_ORG = "improve-imgsli"
_QS_APP = "improve-imgsli"
_QS_KEY = "multi_compare/last_session_settings"

_last_session_settings: "tuple | None" = None  # (divider_settings, label_settings)


def _divider_to_dict(divider) -> dict:
    return {
        "visible": divider.visible,
        "thickness": divider.thickness,
        "color_rgba": list(divider.color_rgba),
    }


def _divider_from_dict(d: dict):
    from tabs.multi_compare.models import MultiCompareDividerSettings

    return MultiCompareDividerSettings(
        visible=d.get("visible", True),
        thickness=d.get("thickness", 4),
        color_rgba=tuple(d.get("color_rgba", [180, 180, 180, 230])),
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
    from tabs.multi_compare.models import MultiCompareLabelSettings

    return MultiCompareLabelSettings(
        font_size_percent=l.get("font_size_percent", 100),
        font_weight=l.get("font_weight", 0),
        text_rgba=tuple(l.get("text_rgba", [255, 255, 255, 255])),
        bg_rgba=tuple(l.get("bg_rgba", [0, 0, 0, 255])),
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
        QSettings(_QS_ORG, _QS_APP).setValue(_QS_KEY, json.dumps(data))
    except Exception:
        logger.exception("mc: failed to save last session settings")


def _load_last_settings():
    try:
        raw = QSettings(_QS_ORG, _QS_APP).value(_QS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        divider = _divider_from_dict(data.get("divider", {}))
        label = _label_from_dict(data.get("label", {}))
        return (divider, label)
    except Exception:
        logger.exception("mc: failed to load last session settings")
        return None


def _default_state():
    from tabs.multi_compare.models import MultiCompareState

    global _last_session_settings
    if _last_session_settings is None:
        _last_session_settings = _load_last_settings()
    if _last_session_settings is not None:
        divider, label = _last_session_settings
        return MultiCompareState(divider_settings=divider, label_settings=label)
    return MultiCompareState()


class MultiCompareTab(TabContract):
    """Self-contained multi-image comparison tab."""

    def __init__(self):
        self._controller = None
        self._widget = None
        self._active_session_id: str | None = None
        self._store_context = None

    @property
    def session_type(self) -> str:
        return "multi_compare"

    @property
    def display_name(self) -> str:
        return "Multi Compare"

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "multi_compare"

    def localized_display_name(self, language: str) -> str:
        from sli_ui_toolkit.i18n import tr

        key = "tab_name"
        translated = tr(key, language)
        return translated if translated != key else self.display_name

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        from tabs.multi_compare.controller import MultiCompareController
        from tabs.multi_compare.widget import MultiCompareWidget

        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        def _lang() -> str:
            settings = getattr(context, "settings", None) or getattr(
                getattr(context, "store", None), "settings", None
            )
            return getattr(settings, "current_language", "en") if settings else "en"

        self._widget = MultiCompareWidget(
            page,
            translate=context.tr,
            lang_provider=_lang,
        )
        def open_export_dialog(**kwargs):
            return context.call_service("open_image_export_dialog", **kwargs)

        self._controller = MultiCompareController(
            self._widget,
            store=context.store,
            translate=context.tr,
            dialog_parent=context.main_window or page,
            open_export_dialog=open_export_dialog,
            context=context,
        )
        self._store_context = context.store
        self._widget.store.subscribe(self._on_widget_state_changed)
        layout.addWidget(self._widget)

        return page

    def _resolve_active_session_id(self, context: TabContext) -> str | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        try:
            session = store.get_active_workspace_session()
        except Exception:
            return None
        if session is None:
            return None
        if getattr(session, "session_type", None) != self.session_type:
            return None
        return getattr(session, "id", None)

    def _snapshot_into(self, session_id: str | None) -> None:
        if session_id is None or self._widget is None:
            return
        store = self._store_context
        if store is None:
            return
        store.set_session_state_slot(
            _STATE_SLOT,
            self._widget.store.state,
            session_id=session_id,
            emit_scope=None,
        )

    def _restore_from(self, session_id: str | None) -> None:
        if self._widget is None:
            return

        store = self._store_context
        if session_id is not None and store is not None:
            state = store.ensure_session_state_slot(
                _STATE_SLOT,
                session_id=session_id,
                factory=_default_state,
            )
        else:
            state = _default_state()
        self._widget.store.replace_state(state)

    def _on_widget_state_changed(self, _action, state) -> None:
        global _last_session_settings
        _last_session_settings = (state.divider_settings, state.label_settings)
        _save_last_settings(state.divider_settings, state.label_settings)
        session_id = self._active_session_id
        store = self._store_context
        if session_id is None or store is None:
            return
        store.set_session_state_slot(
            _STATE_SLOT,
            state,
            session_id=session_id,
            emit_scope=None,
        )

    def on_activated(self, context: TabContext) -> None:
        new_id = self._resolve_active_session_id(context)
        if new_id != self._active_session_id:
            self._snapshot_into(self._active_session_id)
            self._active_session_id = new_id
            self._restore_from(new_id)
        if self._widget:
            self._widget.setFocus()

    def on_deactivated(self, context: TabContext) -> None:
        self._snapshot_into(self._active_session_id)

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        store = getattr(context, "store", None)
        if store is None:
            return
        store.set_session_state_slot(
            _STATE_SLOT,
            _default_state(),
            session_id=session_id,
            emit_scope=None,
        )

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        if self._active_session_id == session_id:
            self._active_session_id = None

    def serialize_session(self, session_id: str, context: TabContext) -> dict | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        session = store.get_workspace_session(session_id)
        if session is None or session.session_type != self.session_type:
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

    def deserialize_session(self, session_id: str, data: dict, context: TabContext) -> None:
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

    def register_canvas_features(self) -> None:
        import tabs.multi_compare.canvas.features as features_pkg
        from ui.canvas_infra.scene.registry import register_canvas_feature_package

        register_canvas_feature_package("multi_compare", features_pkg)

    def _canvas(self):
        if self._widget is None:
            return None
        return self._widget.canvas

    def get_canvas_geometry_provider(self):
        if self._widget is None:
            return None
        from tabs.multi_compare.canvas_geometry_provider import (
            MultiCompareCanvasGeometryProvider,
        )

        return MultiCompareCanvasGeometryProvider(self._canvas)

    def apply_appearance(self, host_window) -> None:
        canvas = self._canvas()
        if canvas is None:
            return
        theme_manager = getattr(host_window, "theme_manager", None)
        if theme_manager is None:
            return
        from PySide6.QtGui import QColor

        from ui.theming import resolve_theme_color

        bg = resolve_theme_color(theme_manager, "label.image.background")
        canvas.apply_theme_background(QColor(bg))
        canvas.update()

    def contribute_settings(self, registry) -> None:

        return

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> None:
        if self._controller:
            image_paths = [p for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
            self._controller.load_images(image_paths)

    def dispose(self) -> None:
        self._controller = None
        self._widget = None
