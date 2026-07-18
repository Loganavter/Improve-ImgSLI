"""Host chrome extension for the session picker page.

Host code (``ui/main_window/project_io``, ``menu_controller``) must not
duck-type the page widget. Resolve via
``resolve_session_picker_host_chrome()`` /
``TabRegistry.create_service_for(INITIAL_WORKSPACE_SESSION_TYPE,
\"session_picker.host_chrome\")``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from PySide6.QtWidgets import QWidget


@runtime_checkable
class SessionPickerHostChrome(Protocol):
    """Narrow surface the host needs from the session picker page."""

    def refresh_recent(self) -> None: ...

    def set_open_project_handler(
        self, handler: Callable[[str], None] | None
    ) -> None: ...

    def card_for(self, session_type: str) -> QWidget | None: ...


class SessionPickerHostChromeAdapter:
    """Forwards to ``SessionPickerWidget`` without exposing the page type."""

    def __init__(self, page: QWidget) -> None:
        self._page = page

    def refresh_recent(self) -> None:
        self._page.refresh_recent()

    def set_open_project_handler(
        self, handler: Callable[[str], None] | None
    ) -> None:
        self._page.set_open_project_handler(handler)

    def card_for(self, session_type: str) -> QWidget | None:
        return self._page.card_for(session_type)
