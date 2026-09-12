"""App-side InspectorWindow: toolkit InspectorWindow + Native diagnostics
page and the Dump-layout buttons (Find-Action-aware, app-specific)."""

from __future__ import annotations

from PySide6.QtCore import QRect, Signal
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.ui.inspector.contract import InspectField
from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from sli_ui_toolkit.widgets import Button, Label

from devtools.ui_inspector.native import NativeWindowInfo


class AppInspectorWindow(InspectorWindow):
    """InspectorWindow extended with the app's native-window diagnostics and
    the Dump-layout buttons."""

    dump_layout_requested = Signal()
    dump_window_layout_requested = Signal()
    toggle_native_window_requested = Signal()
    force_repaint_requested = Signal()
    force_update_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dump_status = Label("", pixel_size=11)
        self._add_dump_buttons()
        # Each inspection tab gets its own Native section.
        self.pane_created.connect(self._add_native_page)
        self._native_widget: QWidget | None = None
        self._native_chain: tuple[NativeWindowInfo, ...] = ()

    def _add_dump_buttons(self) -> None:
        widget_dump = Button(text="Dump widget", variant="default", size=(0, 30))
        widget_dump.setToolTip(
            "Dump the selected widget's subtree (falls back to the whole "
            "window if nothing is selected)"
        )
        widget_dump.clicked.connect(self.dump_layout_requested)
        window_dump = Button(text="Dump window", variant="default", size=(0, 30))
        window_dump.setToolTip("Dump the whole last-focused window layout")
        window_dump.clicked.connect(self.dump_window_layout_requested)
        self.toolbar_layout.addWidget(widget_dump)
        self.toolbar_layout.addWidget(window_dump)
        self.toolbar_layout.addWidget(self._dump_status)

    def _add_native_page(self, pane) -> None:
        page = pane.add_section("Native")

        # Experiment buttons (same three as the legacy panel).
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 4, 8, 2)
        layout.setSpacing(6)
        toggle = Button(text="Toggle native window", variant="default", size=(0, 28))
        toggle.clicked.connect(self.toggle_native_window_requested)
        repaint = Button(text="Force repaint()", variant="default", size=(0, 28))
        repaint.clicked.connect(self.force_repaint_requested)
        update = Button(text="Force update()", variant="default", size=(0, 28))
        update.clicked.connect(self.force_update_requested)
        layout.addWidget(toggle)
        layout.addWidget(repaint)
        layout.addWidget(update)
        layout.addStretch(1)
        page.content_layout.addWidget(row)

    def show_dump_result(self, path: str) -> None:
        self._dump_status.setText(f"dumped: {path} (copied)")

    def set_native_diagnostics(
        self, widget: QWidget | None, chain: tuple[NativeWindowInfo, ...]
    ) -> None:
        self._native_widget = widget
        self._native_chain = chain
        pane = self.active_pane()
        if pane is None or "Native" not in pane.pages:
            return
        page = pane.pages["Native"]
        self._clear(page)
        if widget is None:
            return
        self._add_title(page, "Native window")
        for info in chain:
            self._add_field_row(
                page,
                InspectField(
                    name=info.selector,
                    value=(
                        "native" if info.has_native_window else "no native window"
                        + ("  [QRhiWidget]" if info.is_qrhiwidget else "")
                        + (
                            f"  siblings: {', '.join(info.sibling_qrhiwidgets) or '—'}"
                            if info.sibling_qrhiwidgets
                            else ""
                        )
                    ),
                ),
            )
        page.content_layout.addStretch(1)