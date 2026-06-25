"""Multi-compare tab contract implementation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QVBoxLayout, QWidget

from tabs.contract import TabContext, TabContract

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}

class MultiCompareTab(TabContract):
    """Self-contained multi-image comparison tab."""

    def __init__(self):
        self._controller = None
        self._widget = None
        self._session_states: dict[str, object] = {}
        self._active_session_id: str | None = None

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
            add_images_text=context.tr("add_images", "Add images"),
            save_result_text=context.tr("save_result", "Save result"),
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
        self._session_states[session_id] = self._widget.store.state

    def _restore_from(self, session_id: str | None) -> None:
        if self._widget is None:
            return
        from tabs.multi_compare.models import MultiCompareState
        state = self._session_states.get(session_id) if session_id is not None else None
        if state is None:
            state = MultiCompareState()
            if session_id is not None:
                self._session_states[session_id] = state
        self._widget.store.replace_state(state)

    def on_activated(self, context: TabContext) -> None:
        new_id = self._resolve_active_session_id(context)
        if new_id != self._active_session_id:
            self._snapshot_into(self._active_session_id)
            self._restore_from(new_id)
            self._active_session_id = new_id
        if self._widget:
            self._widget.setFocus()

    def on_deactivated(self, context: TabContext) -> None:
        self._snapshot_into(self._active_session_id)

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        from tabs.multi_compare.models import MultiCompareState
        self._session_states[session_id] = MultiCompareState()

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        self._session_states.pop(session_id, None)
        if self._active_session_id == session_id:
            self._active_session_id = None

    def contribute_settings(self, registry) -> None:
        # Multi-compare currently shares the global appearance/interface/
        # performance sections via the built-in registrations. Tab-specific
        # sections (e.g. grid layout defaults) would be registered here.
        return

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path]) -> None:
        if self._controller:
            image_paths = [p for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
            self._controller.load_images(image_paths)

    def dispose(self) -> None:
        self._controller = None
        self._widget = None
