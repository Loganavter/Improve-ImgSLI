"""Multi-compare tab contract implementation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QVBoxLayout, QWidget

from tabs.contract import TabContext, TabContract

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
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


def _default_state():
    """Blueprint factory: clean defaults only (no in-memory leak)."""
    return _fresh_default_state()


def _multi_compare_session_count(store) -> int:
    return sum(
        1
        for session in store.list_workspace_sessions()
        if getattr(session, "session_type", None) == "multi_compare"
    )


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
    def icon(self) -> QIcon | None:
        from tabs.multi_compare.icons import Icon, get_icon

        return get_icon(Icon.GRID)

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

        # Session may already be active before the deferred page exists. The
        # earlier ``on_active_session_changed`` then no-oped ``_restore_from``
        # (widget was None) and would early-return forever for the same id —
        # leaving the live widget on defaults and wiping QSettings on the next
        # divider edit. Pull the seeded slot now.
        session_id = self._active_session_id or self._resolve_active_session_id(context)
        logger.debug(
            "[mc-divider-persist] create_page widget_ready active_session=%s",
            session_id,
        )
        if session_id is not None:
            self._active_session_id = session_id
            self._restore_from(session_id)

        return page

    def apply_host_session_mode(self, ui, session_title: str | None = None) -> bool:
        return True

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
            logger.debug(
                "[mc-divider-persist] restore skipped (no widget) session=%s",
                session_id,
            )
            return

        store = self._store_context
        if session_id is not None and store is not None:
            state = store.ensure_session_state_slot(
                _STATE_SLOT,
                session_id=session_id,
                factory=_fresh_default_state,
            )
        else:
            state = _fresh_default_state()
        color = getattr(getattr(state, "divider_settings", None), "color_rgba", None)
        logger.debug(
            "[mc-divider-persist] restore → widget session=%s color=%s",
            session_id,
            list(color) if color is not None else None,
        )
        self._widget.store.replace_state(state)

    def _on_widget_state_changed(self, action, state) -> None:
        # Only persist "last used" prefs on intentional divider/label edits.
        # ``replace_state`` (session switch/restore) must not overwrite QSettings
        # with a transient widget default.
        action_type = getattr(action, "type", "")
        if action_type in {
            "multi_compare/set_divider_settings",
            "multi_compare/set_label_settings",
        }:
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
        session_id = self._resolve_active_session_id(context)
        logger.debug(
            "[mc-divider-persist] on_activated session=%s widget=%s",
            session_id,
            self._widget is not None,
        )
        if session_id is not None:
            self.on_active_session_changed(session_id, context)
        if self._widget:
            self._widget.setFocus()
        from ui.actions.registry import get_action_registry

        self._register_actions(get_action_registry())

    def on_active_session_changed(self, session_id: str, context: TabContext) -> None:
        # Skip only when this session is already bound to a live widget whose
        # divider prefs already match the session slot. Workspace activate can
        # fire *before* ``on_session_created`` seeds QSettings into the slot —
        # then a blind early-return would leave the widget on defaults forever.
        if session_id == self._active_session_id and self._widget is not None:
            if self._widget_matches_session_slot(session_id):
                logger.debug(
                    "[mc-divider-persist] active_session skip (already in sync) %s",
                    session_id,
                )
                return
            logger.debug(
                "[mc-divider-persist] active_session re-sync after slot change %s",
                session_id,
            )
            self._restore_from(session_id)
            return
        if (
            self._widget is not None
            and self._active_session_id is not None
            and self._active_session_id != session_id
        ):
            self._snapshot_into(self._active_session_id)
        self._active_session_id = session_id
        logger.debug(
            "[mc-divider-persist] active_session_changed → %s widget=%s",
            session_id,
            self._widget is not None,
        )
        self._restore_from(session_id)

    def _widget_matches_session_slot(self, session_id: str) -> bool:
        if self._widget is None or self._store_context is None:
            return False
        slot = self._store_context.get_session_state_slot(
            _STATE_SLOT, session_id=session_id
        )
        if slot is None:
            return False
        return (
            self._widget.store.state.divider_settings == slot.divider_settings
            and self._widget.store.state.label_settings == slot.label_settings
        )

    def on_deactivated(self, context: TabContext) -> None:
        self._snapshot_into(self._active_session_id)

    def on_session_created(self, session_id: str, context: TabContext) -> None:
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
        # WorkspaceSessionCreatedEvent. The presenter can therefore activate the
        # tab and ``_restore_from`` defaults into the live widget *before* this
        # seed runs. Push the seeded slot into the widget if it is already bound.
        if (
            seeded
            and self._widget is not None
            and (
                self._active_session_id == session_id
                or self._resolve_active_session_id(context) == session_id
            )
        ):
            self._active_session_id = session_id
            self._restore_from(session_id)

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

    def rehydrate_session(self, session_id: str, context: TabContext) -> None:
        store = getattr(context, "store", None)
        if store is None:
            return
        state = store.get_session_state_slot(_STATE_SLOT, session_id=session_id)
        if state is None:
            return

        controller = self._controller
        if controller is None:
            logger.warning(
                "mc: rehydrate_session skipped — controller unavailable for %s",
                session_id,
            )
            return

        if not controller.rehydrate_slots(state):
            return

        if session_id == self._active_session_id and self._widget is not None:
            self._widget.store.replace_state(state)

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

    def _register_actions(self, registry) -> None:
        if self._widget is None:
            return
        from tabs.multi_compare.actions import register_multi_compare_actions

        register_multi_compare_actions(
            toolbar=getattr(self._widget, "toolbar", None),
            footer=getattr(self._widget, "footer", None),
            registry=registry,
        )
        self._resync_action_shortcuts()

    def _resync_action_shortcuts(self) -> None:
        from PySide6.QtWidgets import QApplication

        from ui.actions.binder import resync_action_shortcuts

        for widget in QApplication.topLevelWidgets():
            if getattr(widget, "presenter", None) is not None:
                resync_action_shortcuts(widget, active_tab=self.session_type)
                return

    def create_service(self, service_id: str, *args, **kwargs):
        if service_id == "contribute_settings":
            # No tab-owned settings pages yet.
            return True
        if service_id == "contribute_actions":
            registry = args[0] if args else kwargs.get("registry")
            if registry is None:
                return None
            self._register_actions(registry)
            return True
        if service_id == "contribute_keymap_defaults":
            registry = args[0] if args else kwargs.get("registry")
            if registry is None:
                return None
            from tabs.multi_compare.actions import contribute_keymap_defaults

            contribute_keymap_defaults(registry)
            return True
        if service_id == "contribute_help":
            registry = args[0] if args else kwargs.get("registry")
            if registry is None:
                return None
            from tabs.multi_compare.help import contribute_help

            contribute_help(registry)
            return True
        if service_id == "clipboard_paste_service":
            if self._controller is None:
                return None
            from tabs.multi_compare.services.clipboard import ClipboardService

            return ClipboardService(*args, controller=self._controller, **kwargs)
        if service_id == "begin_pending_image_insert":
            paths = args[0] if args else kwargs.get("paths")
            if paths is None or self._widget is None:
                return False
            image_paths = [
                p for p in (Path(x) for x in paths) if p.suffix.lower() in _IMAGE_EXTENSIONS
            ]
            if not image_paths:
                return False
            self._widget.begin_pending_paste(image_paths)
            return True
        return None

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path], hint: dict | None = None) -> None:
        if self._widget is None:
            return
        image_paths = [p for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
        if image_paths:
            # Same placement UX as external DnD / clipboard paste.
            self._widget.begin_pending_paste(image_paths)

    def dispose(self) -> None:
        self._controller = None
        self._widget = None
