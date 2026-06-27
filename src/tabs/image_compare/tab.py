"""Image-compare tab contract implementation.

Stages 1-10 of MIGRATION_PLAN.md.

The tab owns the page widget (``ImageCompareWidget``) and exposes the
tab-contract lifecycle. The host (``ui.main_window``) still creates
the primitive widgets (buttons, sliders, canvas) and calls
``widget.assemble(ui)`` once those primitives exist; long-term the
intent is to move primitive ownership into this tab as well.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract, TabTransitionHint

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".jxl"}
_STATE_SLOT = "image_compare.state"


class ImageCompareTab(TabContract):
    def __init__(self):
        self._widget: "ImageCompareWidget | None" = None
        self._active_session_id: str | None = None

    @property
    def session_type(self) -> str:
        return "image_compare"

    @property
    def display_name(self) -> str:
        return "Image Compare"

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "image_compare"

    def localized_display_name(self, language: str) -> str:
        from resources.translations import tr

        key = "workspace.session_types.image_compare"
        translated = tr(key, language)
        return translated if translated != key else self.display_name

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        from tabs.image_compare.widget import ImageCompareWidget

        self._widget = ImageCompareWidget(parent, context=context)
        return self._widget

    @property
    def widget(self) -> "ImageCompareWidget | None":
        return self._widget

    def transition_hint(self) -> TabTransitionHint:
        # QRhi warm-up can be long; widen the mask window vs the default 300 ms.
        return TabTransitionHint(
            cover_on_enter=True, min_duration_ms=50, max_duration_ms=400
        )

    def on_activated(self, context: TabContext) -> None:
        new_id = self._resolve_active_session_id(context)
        if new_id != self._active_session_id:
            self._snapshot_into(context, self._active_session_id)
            self._active_session_id = new_id
            self._restore_from(context, new_id)
        if self._widget is not None:
            self._widget.setFocus()
        # The transition mask is released by ImageCompareWidget when the
        # canvas emits ``firstVisualFrameReady`` — no host-side release here.

    def on_deactivated(self, context: TabContext) -> None:
        self._snapshot_into(context, self._active_session_id)

    def on_session_created(self, session_id: str, context: TabContext) -> None:
        # Slot is auto-allocated by SessionBlueprint.state_slots; nothing to do.
        return

    def on_session_closed(self, session_id: str, context: TabContext) -> None:
        if self._active_session_id == session_id:
            self._active_session_id = None

    def _resolve_active_session_id(self, context: TabContext) -> str | None:
        store = getattr(context, "store", None)
        if store is None:
            return None
        try:
            session = store.get_active_workspace_session()
        except Exception:
            return None
        if session is None or getattr(session, "session_type", None) != self.session_type:
            return None
        return getattr(session, "id", None)

    def _snapshot_into(self, context: TabContext, session_id: str | None) -> None:
        if session_id is None or self._widget is None:
            return
        store = getattr(context, "store", None)
        if store is None or not hasattr(store, "set_session_state_slot"):
            return
        ui = getattr(self._widget._context, "main_window", None) if self._widget._context else None
        ui = getattr(ui, "ui", None) if ui is not None else None
        if ui is None:
            return
        from tabs.image_compare.models import ImageCompareState

        state = ImageCompareState(
            show_file_names=bool(getattr(getattr(ui, "btn_file_names", None), "isChecked", lambda: False)()),
            edit_name_1=getattr(getattr(ui, "edit_name1", None), "text", lambda: "")(),
            edit_name_2=getattr(getattr(ui, "edit_name2", None), "text", lambda: "")(),
        )
        try:
            store.set_session_state_slot(
                _STATE_SLOT, state, session_id=session_id, emit_scope=None,
            )
        except Exception:
            pass

    def _restore_from(self, context: TabContext, session_id: str | None) -> None:
        if session_id is None or self._widget is None:
            return
        store = getattr(context, "store", None)
        if store is None or not hasattr(store, "ensure_session_state_slot"):
            return
        from tabs.image_compare.models import ImageCompareState

        try:
            state = store.ensure_session_state_slot(
                _STATE_SLOT, session_id=session_id, factory=ImageCompareState,
            )
        except Exception:
            return
        if state is None:
            return
        ui = getattr(self._widget._context, "main_window", None) if self._widget._context else None
        ui = getattr(ui, "ui", None) if ui is not None else None
        if ui is None:
            return
        btn = getattr(ui, "btn_file_names", None)
        if btn is not None and hasattr(btn, "setChecked"):
            btn.setChecked(bool(state.show_file_names))
        for attr, value in (("edit_name1", state.edit_name_1), ("edit_name2", state.edit_name_2)):
            edit = getattr(ui, attr, None)
            if edit is not None and hasattr(edit, "setText"):
                edit.setText(value or "")

    def accepts_drop(self, paths: list[Path]) -> bool:
        return any(p.suffix.lower() in _IMAGE_EXTENSIONS for p in paths)

    def handle_drop(self, paths: list[Path]) -> None:
        # The WindowEventHandler currently keeps the slot-aware drop fallback
        # for image_compare, so returning False from accepts_drop is also valid.
        # We accept the drop here so that the contract advertises the capability;
        # the actual slot routing is still done by the host until Stage 5 lands
        # full per-session state ownership in this tab.
        from PySide6.QtCore import QTimer

        widget = self._widget
        if widget is None:
            return
        main_window = getattr(widget._context, "main_window", None) if widget._context else None
        if main_window is None:
            return
        controller = getattr(main_window, "main_controller", None)
        sessions = getattr(controller, "sessions", None) if controller else None
        if sessions is None:
            return
        image_paths = [str(p) for p in paths if p.suffix.lower() in _IMAGE_EXTENSIONS]
        if not image_paths:
            return
        QTimer.singleShot(
            0, lambda: sessions.load_images_from_paths(image_paths, 1)
        )

    def contribute_settings(self, registry) -> None:
        from plugins.settings.pages.analysis import build as build_analysis
        from plugins.settings.registry import SettingsSection
        from ui.icon_manager import AppIcon

        registry.add(
            SettingsSection(
                section_id="image_compare.analysis",
                title_key="label.details",
                icon=AppIcon.HIGHLIGHT_DIFFERENCES,
                build=build_analysis,
                owner_tab=self.session_type,
                order=40,
            )
        )

    def dispose(self) -> None:
        self._widget = None
