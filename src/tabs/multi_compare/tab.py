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


def _save_last_settings(divider, label) -> None:
    from tabs.multi_compare.models import MultiCompareDividerSettings, MultiCompareLabelSettings
    try:
        data = {
            "divider": {
                "visible": divider.visible,
                "thickness": divider.thickness,
                "color_rgba": list(divider.color_rgba),
            },
            "label": {
                "font_size_percent": label.font_size_percent,
                "font_weight": label.font_weight,
                "text_rgba": list(label.text_rgba),
                "bg_rgba": list(label.bg_rgba),
                "draw_background": label.draw_background,
                "text_alpha_percent": label.text_alpha_percent,
            },
        }
        QSettings(_QS_ORG, _QS_APP).setValue(_QS_KEY, json.dumps(data))
        logger.warning(
            "[divider-color-debug] _save_last_settings: color_rgba=%s",
            data["divider"]["color_rgba"],
        )
    except Exception:
        logger.exception("mc: failed to save last session settings")


def _load_last_settings():
    from tabs.multi_compare.models import MultiCompareDividerSettings, MultiCompareLabelSettings
    try:
        raw = QSettings(_QS_ORG, _QS_APP).value(_QS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        d = data.get("divider", {})
        l = data.get("label", {})
        divider = MultiCompareDividerSettings(
            visible=d.get("visible", True),
            thickness=d.get("thickness", 4),
            color_rgba=tuple(d.get("color_rgba", [180, 180, 180, 230])),
        )
        label = MultiCompareLabelSettings(
            font_size_percent=l.get("font_size_percent", 100),
            font_weight=l.get("font_weight", 0),
            text_rgba=tuple(l.get("text_rgba", [255, 255, 255, 255])),
            bg_rgba=tuple(l.get("bg_rgba", [0, 0, 0, 255])),
            draw_background=l.get("draw_background", True),
            text_alpha_percent=l.get("text_alpha_percent", 100),
        )
        logger.warning(
            "[divider-color-debug] _load_last_settings: color_rgba=%s",
            divider.color_rgba,
        )
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
        logger.warning(
            "[divider-color-debug] _default_state: using cached/loaded color_rgba=%s",
            divider.color_rgba,
        )
        return MultiCompareState(divider_settings=divider, label_settings=label)
    logger.warning("[divider-color-debug] _default_state: falling back to built-in default")
    return MultiCompareState()


class MultiCompareTab(TabContract):
    """Self-contained multi-image comparison tab."""

    def __init__(self):
        self._controller = None
        self._widget = None
        self._session_states: dict[str, object] = {}
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
        self._controller = MultiCompareController(
            self._widget,
            store=context.store,
            translate=context.tr,
            dialog_parent=context.main_window or page,
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
        state = self._widget.store.state
        self._session_states[session_id] = state
        store = self._store_context
        if store is not None and hasattr(store, "set_session_state_slot"):
            store.set_session_state_slot(
                _STATE_SLOT,
                state,
                session_id=session_id,
                emit_scope=None,
            )

    def _restore_from(self, session_id: str | None) -> None:
        if self._widget is None:
            return

        state = None
        store = self._store_context
        if (
            session_id is not None
            and store is not None
            and hasattr(store, "ensure_session_state_slot")
        ):
            state = store.ensure_session_state_slot(
                _STATE_SLOT,
                session_id=session_id,
                factory=_default_state,
            )
        if state is None and session_id is not None:
            state = self._session_states.get(session_id)
        if state is None:
            state = _default_state()
            if session_id is not None:
                self._session_states[session_id] = state
        logger.warning(
            "[divider-color-debug] _restore_from session_id=%s color_rgba=%s",
            session_id, state.divider_settings.color_rgba,
        )
        self._widget.store.replace_state(state)

    def _on_widget_state_changed(self, _action, state) -> None:
        global _last_session_settings
        _last_session_settings = (state.divider_settings, state.label_settings)
        _save_last_settings(state.divider_settings, state.label_settings)
        session_id = self._active_session_id
        logger.warning(
            "[divider-color-debug] _on_widget_state_changed: action=%s session_id=%s color_rgba=%s",
            getattr(_action, "type", _action), session_id, state.divider_settings.color_rgba,
        )
        if session_id is None:
            return
        self._session_states[session_id] = state
        store = self._store_context
        if store is None or not hasattr(store, "set_session_state_slot"):
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
        state = _default_state()
        self._session_states[session_id] = state
        store = getattr(context, "store", None)
        if store is not None and hasattr(store, "set_session_state_slot"):
            store.set_session_state_slot(
                _STATE_SLOT,
                state,
                session_id=session_id,
                emit_scope=None,
            )

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        self._session_states.pop(session_id, None)
        if self._active_session_id == session_id:
            self._active_session_id = None

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
