"""Tab-level Ask AI sidebar host — the gallery's dock-like right-hand panel.

There was no reusable in-tab sidebar host in the gallery (the right side is the
grid itself; Quick Look / Clean Review are overlays), so this is the minimal
container the task asks for: a header row (title + close) and one content well
that embeds the **shared** ``AskAiSurface`` instance. It is not a second flyout
and does not re-implement the ask body: when the sidebar shows, the surface is
reparented out of the flyout shell into this panel; when the flyout opens, it
takes the same instance back.

Shown/hidden from the workspace via the gallery toolbar's AI toggle
(``ui/widget_parts/ask_ai_sidebar.py`` owns that wiring). The close button and
the embedded rows are owned by ``ui/ask_nav.py`` while the panel is visible.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, SurfaceScrollArea, Text

from tabs.image_gallery.ui import ask_nav
from ui.widgets.shelf.widget import OpaqueFillHost


class AskAiSidebar(OpaqueFillHost):
    """Dock-like panel hosting the shared Ask AI surface."""

    #: The user dismissed the panel (its ✕); the gallery hosts the toggle state.
    closed = Signal()

    def __init__(self, parent: QWidget | None = None, *, title: str = "Ask AI") -> None:
        super().__init__(parent)
        self._surface = None
        self.setObjectName("gallery_ask_sidebar")
        try:
            self.setMinimumWidth(scaled_px(300))
            self.setMaximumWidth(scaled_px(460))
        except Exception:
            pass

        root = QVBoxLayout(self)
        root.setContentsMargins(
            scaled_px(10), scaled_px(10), scaled_px(10), scaled_px(10)
        )
        root.setSpacing(scaled_px(8))

        self._header_row = QWidget(self)
        self._header_row.setObjectName("gallery_ask_sidebar_header")
        header = QHBoxLayout(self._header_row)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scaled_px(6))
        self._title = Text(title, mode="plain", pixel_size=13, bold=True, parent=self._header_row)
        self._title.setObjectName("gallery_ask_sidebar_title")
        header.addWidget(self._title, 1)
        self._close_btn = Button(text="✕", variant="surface", size=(28, 28), parent=self._header_row)
        self._close_btn.setObjectName("gallery_ask_sidebar_close")
        try:
            self._close_btn.clicked.connect(self._on_close_clicked)
        except Exception:
            pass
        header.addWidget(self._close_btn, 0)
        root.addWidget(self._header_row)

        # Toolkit surface scroll area: a long answer scrolls inside the docked
        # panel instead of growing it past the window.
        self._scroll = SurfaceScrollArea(self, surface_token="surface.background")
        self._scroll.setObjectName("gallery_ask_sidebar_scroll")
        try:
            self._scroll.setWidgetResizable(True)
            self._scroll.setFrameShape(QFrame.Shape.NoFrame)
            self._scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        except Exception:
            pass
        root.addWidget(self._scroll, 1)
        self.hide()

    # -- shared surface -----------------------------------------------------

    def attach_surface(self, surface) -> None:  # type: ignore[no-untyped-def]
        """Embed *surface* in the panel's content well (one instance)."""
        if surface is None:
            return
        # The flyout shell may still own the shared instance; take it back.
        try:
            owner = self.parentWidget()
            flyout = getattr(owner, "_ask_ai_flyout", None)
            if flyout is not None and flyout.surface() is surface:
                flyout.detach_surface()
        except Exception:
            pass
        try:
            current = self._scroll.takeWidget()
            if current is not None and current is not surface:
                try:
                    current.hide()
                except Exception:
                    pass
                current.setParent(None)
                try:
                    current.hide()
                except Exception:
                    pass
        except Exception:
            pass
        self._surface = surface
        try:
            self._scroll.setWidget(surface)
            surface.setVisible(True)
        except Exception:
            pass
        try:
            from tabs.image_gallery.ui.ask_surface import AskAiSurface

            if isinstance(surface, AskAiSurface):
                # The panel header already names the surface; no duplicate title.
                surface.set_title_visible(False)
        except Exception:
            pass
        if self.isVisible():
            ask_nav.register(self, surface)

    def detach_surface(self):  # type: ignore[no-untyped-def]
        """Hand the surface back (the flyout is taking it)."""
        surface = self._surface
        if surface is None:
            return None
        try:
            self._scroll.takeWidget()
        except Exception:
            pass
        self._surface = None
        ask_nav.unregister(self)
        return surface

    def surface(self):  # type: ignore[no-untyped-def]
        """The embedded shared surface (``None`` before first attach)."""
        return self._surface

    def focus_question(self) -> None:
        """Move the caret into the embedded question field."""
        surface = self._surface
        if surface is None:
            return
        try:
            surface.focus_question()
        except Exception:
            pass

    # -- chrome -------------------------------------------------------------

    def nav_chrome_rows(self) -> list:
        """Chrome rows owned by the ask navigation section (the ✕)."""
        return [getattr(self, "_close_btn", None)]

    def set_texts(self, *, title: str | None = None, close: str | None = None) -> None:
        """Inject localized chrome strings (title + close tooltip)."""
        if title:
            try:
                self._title.setText(str(title))
            except Exception:
                pass
        if close:
            try:
                self._close_btn.setToolTip(str(close))
            except Exception:
                pass

    def _on_close_clicked(self) -> None:
        self.hide()

    # -- lifecycle ----------------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().showEvent(event)
        if self._surface is not None:
            ask_nav.register(self, self._surface)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().hideEvent(event)
        ask_nav.unregister(self)
        try:
            self.closed.emit()
        except Exception:
            pass


__all__ = ["AskAiSidebar"]
