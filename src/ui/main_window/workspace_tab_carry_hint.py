"""Accent wiggle on workspace tabs that accept an in-progress image Move."""

from __future__ import annotations

import math
from pathlib import Path

import shiboken6 as sip
from PySide6.QtCore import QPoint, QRect, QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from shared_toolkit.ui.overlay_layer import get_overlay_layer
from sli_ui_toolkit.theme import ThemeManager
from ui.theming import resolve_theme_color

_TICK_MS = 33
_WIGGLE_PX = 2.5


class _TabCarryHintOverlay(QWidget):
    """Paints ON the strip tabs BY DESIGN — the intentional exception to the
    content-below-strip rule (plan-2026-09-25-content-below-strip, phase 2):
    this hint wiggles the strip tab rings that accept an in-progress image
    Move, so it must live on the tab-strip band itself. Host resolution stays
    window-layer; only the overlay geometry is narrowed to the tabs rect."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspaceTabCarryHint")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._rects: list[tuple[QRect, bool]] = []
        self._phase = 0.0
        self.hide()

    def set_targets(self, rects: list[tuple[QRect, bool]], *, phase: float) -> None:
        parent = self.parentWidget()
        if parent is None:
            self._rects = list(rects)
            self._phase = phase
            if self._rects:
                self.show()
                self.update()
            else:
                self.hide()
            return
        try:
            geometry = self._tabs_geometry(parent)
        except Exception:
            geometry = None
        if geometry is None:
            geometry = parent.rect()
        self.setGeometry(geometry)
        # Incoming rects arrive in parent coords (tab_bar.mapTo(parent));
        # re-base them to overlay-local coords so the paint output is
        # identical now that the overlay origin is the tabs top-left.
        try:
            offset = geometry.topLeft()
            if offset != QPoint(0, 0):
                self._rects = [
                    (QRect(r.topLeft() - offset, r.size()), hovered)
                    for r, hovered in rects
                    if isinstance(r, QRect) and r.isValid()
                ]
            else:
                self._rects = list(rects)
        except Exception:
            self._rects = list(rects)
        self._phase = phase
        if self._rects:
            self.show()
            self.raise_()
            self.update()
        else:
            self.hide()

    @staticmethod
    def _tabs_geometry(parent: QWidget) -> QRect | None:
        """Tabs widget rect mapped into parent coords; None → legacy host rect."""
        try:
            ui = getattr(parent, "ui", None)
            tabs = getattr(ui, "workspace_tabs", None)
            if tabs is None:
                tabs = getattr(parent, "workspace_tabs", None)
            if tabs is None:
                return None
            top_left = tabs.mapTo(parent, QPoint(0, 0))
            tabs_rect = QRect(top_left, tabs.size())
            if not tabs_rect.isValid():
                return None
            clipped = tabs_rect.intersected(parent.rect())
            return clipped if not clipped.isNull() else None
        except Exception:
            return None

    def paintEvent(self, _event) -> None:  # noqa: ARG002 — Qt API
        if not self._rects:
            return
        try:
            accent = resolve_theme_color(ThemeManager.get_instance(), "accent")
        except Exception:
            accent = QColor("#3d8bfd")
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for rect, hovered in self._rects:
                if not rect.isValid():
                    continue
                wobble = int(round(math.sin(self._phase) * _WIGGLE_PX))
                drawn = rect.translated(wobble, 0)
                alpha = 230 if hovered else 150
                fill_a = 70 if hovered else 35
                ring = QColor(accent)
                ring.setAlpha(alpha)
                fill = QColor(accent)
                fill.setAlpha(fill_a)
                painter.setPen(QPen(ring, 2 if hovered else 1.5))
                painter.setBrush(fill)
                painter.drawRoundedRect(drawn.adjusted(1, 1, -2, -2), 5, 5)
        finally:
            painter.end()


class WorkspaceTabCarryHint:
    """Lifecycle helper: start while Move is active, stop on cancel/deliver."""

    def __init__(self) -> None:
        self._overlay: _TabCarryHintOverlay | None = None
        self._timer: QTimer | None = None
        self._tabs = None
        self._store = None
        self._paths: list[Path] = []
        self._phase = 0.0
        self._hover_index = -1

    def start(self, main_window, store, paths: list[Path]) -> None:
        self.stop()
        self._store = store
        self._paths = list(paths)
        ui = getattr(main_window, "ui", None)
        tabs = getattr(ui, "workspace_tabs", None) if ui is not None else None
        if tabs is None or main_window is None:
            return
        overlay_layer = get_overlay_layer(main_window)
        host = overlay_layer.host if overlay_layer is not None else main_window
        self._tabs = tabs
        self._overlay = _TabCarryHintOverlay(host)
        self._timer = QTimer(self._overlay)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._refresh()

    def update_hover(self, global_pos: QPoint) -> None:
        tabs = self._tabs
        if tabs is None:
            return
        tab_bar = getattr(tabs, "tab_bar", None)
        if tab_bar is None:
            return
        local = tab_bar.mapFromGlobal(global_pos)
        index = tab_bar.tabAt(local) if tab_bar.rect().contains(local) else -1
        if index != self._hover_index:
            self._hover_index = index
            self._refresh()

    def stop(self) -> None:
        if self._timer is not None:
            try:
                self._timer.stop()
                self._timer.deleteLater()
            except RuntimeError:
                pass
            self._timer = None
        if self._overlay is not None:
            try:
                if sip.isValid(self._overlay):
                    self._overlay.hide()
                    self._overlay.deleteLater()
            except RuntimeError:
                pass
            self._overlay = None
        self._tabs = None
        self._store = None
        self._paths = []
        self._phase = 0.0
        self._hover_index = -1

    def _tick(self) -> None:
        self._phase += 0.35
        self._refresh()

    def _refresh(self) -> None:
        if self._overlay is None or not sip.isValid(self._overlay):
            return
        tabs = self._tabs
        store = self._store
        if tabs is None or store is None:
            return
        tab_bar = getattr(tabs, "tab_bar", None)
        if tab_bar is None:
            return
        from tabs.registry import TabRegistry

        registry = TabRegistry()
        targets: list[tuple[QRect, bool]] = []
        for index in range(tabs.count()):
            session_id = tabs.tabData(index)
            if not session_id:
                continue
            session = store.get_workspace_session(session_id)
            if session is None:
                continue
            session_type = getattr(session, "session_type", "") or ""
            tab = registry.get_tab(session_type)
            if tab is None or not tab.accepts_drop(self._paths):
                continue
            rect = tab_bar.tabRect(index)
            top_left = tab_bar.mapTo(self._overlay.parentWidget(), rect.topLeft())
            mapped = QRect(top_left, rect.size())
            targets.append((mapped, index == self._hover_index))
        self._overlay.set_targets(targets, phase=self._phase)
