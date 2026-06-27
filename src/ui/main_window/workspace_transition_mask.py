"""Host-level paint mask used to hide intermediate paint glitches during
workspace tab transitions.

The mask is a solid-color overlay parented to the main window. It covers a
target widget (typically the workspace stack) for a short, bounded window so
that complex tab pages don't expose half-rendered intermediate layouts.

Contract: any tab that opts into the mask (``cover_on_enter=True``) MUST
report first-frame readiness by calling :meth:`release` on this service.
``max_duration_ms`` is not a quiet fallback — it is a hard contract-violation
deadline. When it fires without a prior ``release()`` the mask is forcibly
removed AND a contract violation is logged (and, in dev builds, raised), so
the missing readiness signal is loud, not invisible.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget

from ui.theming import resolve_theme_color

logger = logging.getLogger("ImproveImgSLI")


class TabTransitionContractError(RuntimeError):
    """Raised when a tab fails to report first-frame readiness in time."""


def _strict_mode() -> bool:
    return os.environ.get("IMPROVE_IMGSLI_STRICT_CONTRACTS", "").lower() in (
        "1",
        "true",
        "yes",
    )


class WorkspaceTransitionMask:
    def __init__(self, main_window: QWidget):
        self._main_window = main_window
        self._overlay: QWidget | None = None
        self._min_timer = QTimer(main_window)
        self._min_timer.setSingleShot(True)
        self._min_timer.timeout.connect(self._on_min_elapsed)
        self._max_timer = QTimer(main_window)
        self._max_timer.setSingleShot(True)
        self._max_timer.timeout.connect(self._on_max_elapsed)
        self._min_elapsed = True
        self._release_requested = False
        self._active = False
        self._current_session_type: str | None = None
        self._current_max_ms: int = 0

    def cover(
        self,
        target: QWidget | None,
        *,
        min_duration_ms: int = 50,
        max_duration_ms: int = 300,
        session_type: str | None = None,
    ) -> None:
        if target is None:
            return
        overlay = self._ensure_overlay()
        if overlay is None:
            return

        bg = QColor(resolve_theme_color(self._main_window.theme_manager, "Window"))
        if bg.isValid():
            pal = overlay.palette()
            pal.setColor(QPalette.ColorRole.Window, bg)
            overlay.setPalette(pal)

        top_left = target.mapTo(self._main_window, target.rect().topLeft())
        overlay.setGeometry(
            top_left.x(), top_left.y(), target.width(), target.height()
        )
        overlay.raise_()
        overlay.show()
        overlay.repaint()

        min_ms = max(0, int(min_duration_ms))
        max_ms = max(min_ms, int(max_duration_ms))

        self._min_elapsed = False
        self._release_requested = False
        self._active = True
        self._current_session_type = session_type
        self._current_max_ms = max_ms
        self._min_timer.start(min_ms)
        self._max_timer.start(max_ms)

    def release(self) -> None:
        """Report first-frame readiness. Mandatory for any tab with
        ``cover_on_enter=True``. Honored only after ``min_duration_ms``
        has elapsed; before that, the request is queued."""
        if not self._active:
            return
        self._release_requested = True
        if self._min_elapsed:
            self._finish(violated=False)

    def _on_min_elapsed(self) -> None:
        self._min_elapsed = True
        if self._release_requested:
            self._finish(violated=False)

    def _on_max_elapsed(self) -> None:
        if not self._active:
            return
        self._finish(violated=True)

    def _finish(self, *, violated: bool) -> None:
        self._min_timer.stop()
        self._max_timer.stop()
        self._active = False
        if self._overlay is not None:
            self._overlay.hide()
        if not violated:
            return

        session = self._current_session_type or "<unknown>"
        budget = self._current_max_ms
        message = (
            "Tab '%s' did not report first-frame readiness within %d ms — "
            "transition_hint contract violated. The tab must call "
            "context.services['workspace.transition_mask'].release() once "
            "its first valid frame is painted, or override transition_hint() "
            "to set cover_on_enter=False."
        )
        logger.error(message, session, budget)
        if _strict_mode():
            raise TabTransitionContractError(
                f"Tab '{session}' missed transition readiness within {budget} ms"
            )

    def _ensure_overlay(self) -> QWidget | None:
        if self._overlay is not None:
            return self._overlay
        overlay = QWidget(self._main_window)
        overlay.setAutoFillBackground(True)
        overlay.hide()
        self._overlay = overlay
        return overlay
