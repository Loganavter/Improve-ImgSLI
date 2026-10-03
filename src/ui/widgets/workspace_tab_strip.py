"""Workspace-specific tab strip behavior."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QTabBar

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import (
    AdaptiveTabStrip,
    CloseButtonPolicy,
)
from sli_ui_toolkit.widgets import ThemedWidget
from ui.theming import try_resolve_theme_color


class WorkspaceTabStrip(ThemedWidget, AdaptiveTabStrip):
    """Adaptive tabs with browser-like close interactions.

    Eats mouse presses that land on a tab's close-button slot so
    ``_AdaptiveTabBar`` does not activate the tab on press while the close
    button is being clicked.  Without this, clicking the X on an inactive
    tab briefly switches to that tab (currentChanged on press) before the
    close is processed on release, flashing the closed tab's page for one
    frame.

    The strip paints its own background from the ``button.toggle.background.normal``
    token (QSS retired; the tab bar above it paints the same token).
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("close_policy", CloseButtonPolicy.ALL)
        self._strip_bg_color = QColor()
        self._qdrag_drop_handler = None
        super().__init__(*args, **kwargs)
        self._read_strip_color()
        self.tab_bar.installEventFilter(self)
        # Wave C: gallery-card QDrag delivery. The tab bar is the real drop
        # surface (deepest widget under the cursor); the strip itself accepts
        # too so padding around the bar still routes. Mime gating lives in
        # _has_gallery_mime — only the gallery-internal mime is ever claimed,
        # so file/URL drags keep flowing to the window-level overlay.
        try:
            self.setAcceptDrops(True)
        except Exception:
            pass
        try:
            self.tab_bar.setAcceptDrops(True)
        except Exception:
            pass

    def set_qdrag_drop_handler(self, handler) -> None:
        """Duck-typed QDrag drop hook for gallery-card tab delivery (Wave C).

        *handler* is ``callable(event) -> None`` and settles the event itself
        (accept/ignore); the router lives in ``ui.main_window.tab_strip_drop``
        so this widget never imports store/registry code. Fail-open: None (or
        any non-callable) leaves the strip accepting nothing new — drops are
        ignored, never misdelivered.
        """
        try:
            self._qdrag_drop_handler = handler if callable(handler) else None
        except Exception:
            pass

    def _has_gallery_mime(self, mime) -> bool:
        """True when *mime* carries gallery-internal dragged paths.

        The wire format lives in ``ui.main_window.tab_strip_drop``
        (``GALLERY_CARD_MIME`` — itself a mirror of the single tab-side
        definition, pinned equal by test). This widget never imports past
        ``tabs.registry``/``tabs.contract`` (host sandbox contract) — the
        import below stays inside ``ui.*``. Lazy so construction never pays
        for the router module.
        """
        try:
            from ui.main_window.tab_strip_drop import GALLERY_CARD_MIME
        except Exception:
            return False
        try:
            return bool(mime is not None and mime.hasFormat(GALLERY_CARD_MIME))
        except Exception:
            return False

    def _handle_strip_drag_move(self, event) -> bool:
        """Claim enter/move for gallery drags only; True = consumed."""
        try:
            if self._has_gallery_mime(event.mimeData()):
                event.acceptProposedAction()
                return True
        except Exception:
            pass
        return False

    def _handle_strip_drop(self, event) -> bool:
        """Delegate gallery drops to the router hook; True = consumed."""
        try:
            if not self._has_gallery_mime(event.mimeData()):
                return False
        except Exception:
            return False
        handler = getattr(self, "_qdrag_drop_handler", None)
        if not callable(handler):
            try:
                event.ignore()
            except Exception:
                pass
            return True
        try:
            handler(event)
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass
        return True

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        # Strip padding outside the tab bar (the bar itself is covered by the
        # eventFilter branch below).
        if self._handle_strip_drag_move(event):
            return
        try:
            super().dragEnterEvent(event)
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._handle_strip_drag_move(event):
            return
        try:
            super().dragMoveEvent(event)
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass

    def dropEvent(self, event) -> None:  # noqa: N802
        if self._handle_strip_drop(event):
            return
        try:
            super().dropEvent(event)
        except Exception:
            try:
                event.ignore()
            except Exception:
                pass

    def _read_strip_color(self) -> None:
        try:
            resolved = try_resolve_theme_color(
                self._theme_manager, "surface.list"
            )
        except Exception:
            resolved = None
        if resolved is not None and resolved.isValid():
            self._strip_bg_color = QColor(resolved)
        else:
            self._strip_bg_color = QColor(self.palette().window().color())

    def on_theme_changed(self) -> None:
        self._read_strip_color()
        super().on_theme_changed()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._strip_bg_color)
        painter.end()

    def _close_slot_at(self, pos):
        index = self.tab_bar.tabAt(pos)
        if index < 0:
            return None, -1
        slot = self.tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
        if slot is None or not slot.isVisible():
            return None, -1
        slot_rect = slot.geometry()
        if slot_rect.contains(pos):
            return slot, index
        return None, -1

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.tab_bar:
            try:
                _t = event.type()
            except Exception:
                _t = None
            # Wave C: the tab bar is the real QDrag surface — claim
            # gallery-internal drags here so they never fall through to the
            # window file-drop overlay; other mimes propagate untouched.
            if _t == QEvent.Type.DragEnter or _t == QEvent.Type.DragMove:
                if self._handle_strip_drag_move(event):
                    return True
            elif _t == QEvent.Type.Drop:
                if self._handle_strip_drop(event):
                    return True
            if event.type() == QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.MiddleButton:
                    index = self.tab_bar.tabAt(event.pos())
                    if index >= 0:
                        self.tabCloseRequested.emit(index)
                        event.accept()
                        return True
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                _slot, idx = self._close_slot_at(event.pos())
                if idx >= 0:
                    # Eat the press so _AdaptiveTabBar doesn't activate the
                    # tab on mousePress while the X-button is still being
                    # clicked.  The inner close button's own ``clicked``
                    # signal handles the close on mouseRelease.
                    event.accept()
                    return True
        return super().eventFilter(watched, event)


WorkspaceTabStrip.inspect_spec = InspectSpec(
    family="WorkspaceTabStrip",
    state=(
        SpecField("tab_count", lambda w: w.count()),
        SpecField("current_index", lambda w: w.currentIndex()),
    ),
    docs="docs/dev/widgets/workspace_tab_strip.md",
)