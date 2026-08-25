"""New-session picker tab contract implementation."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from tabs.contract import TabContext, TabContract, TabTransitionHint
from tabs.session_picker.widget import SessionPickerWidget


class SessionPickerTab(TabContract):
    startup_tier = "bootstrap"

    @property
    def is_bootstrap_default(self) -> bool:
        # session_picker backs the app's initial workspace session
        # (`core.store.INITIAL_WORKSPACE_SESSION_TYPE`), so it is the sole
        # holder of the bootstrap-default role. TabRegistry enforces that no
        # other tab may claim it.
        return True

    @property
    def session_type(self) -> str:
        return "session_picker"

    @property
    def display_name(self) -> str:
        return "New Tab"

    def localized_display_name(self, language: str) -> str:
        from sli_ui_toolkit.i18n import tr

        key = "session_picker.tab_name"
        translated = tr(key, language)
        return translated if translated != key else self.display_name

    @property
    def resources_dir(self) -> Path | None:
        return Path(__file__).parent / "resources"

    @property
    def i18n_namespace(self) -> str | None:
        return "session_picker"

    def transition_hint(self) -> TabTransitionHint:
        # Lightweight page — no first-frame readiness signal wired yet.
        return TabTransitionHint(cover_on_enter=False)

    def create_page(self, parent: QWidget, context: TabContext) -> QWidget:
        return SessionPickerWidget(parent, context=context)

    def create_service(self, service_id: str, *args, **kwargs):
        if service_id == "session_picker.host_chrome":
            from tabs.registry import TabRegistry
            from tabs.session_picker.host_chrome import SessionPickerHostChromeAdapter

            page = TabRegistry().get_page(self.session_type)
            if page is None:
                return None
            return SessionPickerHostChromeAdapter(page)
        return None

    def apply_host_session_mode(self, ui, session_title: str | None = None) -> bool:
        return True

    def on_host_revealed(self) -> None:
        """Refresh opaque fills and recent panel after host becomes visible."""
        page = self._widget
        if page is None:
            from tabs.registry import TabRegistry

            page = TabRegistry().get_page(self.session_type)
        if page is None:
            return
        # Use public widget API first; private getattr fallback kept only for
        # transition while widget migrates to explicit methods.
        recover = getattr(page, "_sync_opaque_page_fills", None)
        if callable(recover):
            recover()
        if hasattr(page, "refresh") and callable(getattr(page, "refresh")):
            page.refresh()  # type: ignore[attr-defined]
        recent = getattr(page, "_recent_panel", None)
        if recent is not None:
            on_shown = getattr(recent, "on_page_shown", None)
            if callable(on_shown):
                on_shown()
            recover_recent = getattr(recent, "recover_opaque_surface", None)
            if callable(recover_recent):
                recover_recent()
        page.update()

    def dispose(self) -> None:
        self._widget = None