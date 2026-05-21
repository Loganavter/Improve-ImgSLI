from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QTextEdit, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar

@dataclass(frozen=True)
class LogConsoleEntry:
    level: str
    text: str
    color: str | None = None
    bold: bool = False
    italic: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

class LogConsoleWidget(QWidget):
    def __init__(self, parent=None, *, max_entries: int = 1000):
        super().__init__(parent)
        self._max_entries = max(1, int(max_entries))
        self._entries: list[LogConsoleEntry] = []
        self.theme_manager = ThemeManager.get_instance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.output = QTextEdit(self)
        self.output.setObjectName("LogConsoleOutput")
        self.output.setReadOnly(True)
        self.output.setAcceptRichText(False)
        self.output.setUndoRedoEnabled(False)
        self.output.setTabChangesFocus(True)
        self.output.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.output.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        self.output.setCursorWidth(0)

        scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self.output)
        self.output.setVerticalScrollBar(scrollbar)
        self.output.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        layout.addWidget(self.output)

        self.theme_manager.theme_changed.connect(self._apply_styles)
        self._apply_styles()

    def set_max_entries(self, max_entries: int) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries = self._entries[-self._max_entries :]
        self._rebuild()

    def clear(self) -> None:
        self._entries.clear()
        self.output.clear()

    def entries(self) -> tuple[LogConsoleEntry, ...]:
        return tuple(self._entries)

    def history(self) -> tuple[LogConsoleEntry, ...]:
        return self.entries()

    def plain_text_history(self) -> tuple[str, ...]:
        return tuple(entry.text for entry in self._entries)

    def full_text(self, *, separator: str = "\n") -> str:
        return separator.join(self.plain_text_history())

    def append_message(
        self,
        text: str,
        *,
        level: str = "info",
        color: str | QColor | None = None,
        bold: bool = False,
        italic: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> LogConsoleEntry:
        entry = LogConsoleEntry(
            level=self._normalize_level(level),
            text=str(text),
            color=self._normalize_color(color),
            bold=bool(bold),
            italic=bool(italic),
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)
        self._entries = self._entries[-self._max_entries :]
        self.output.append(self._entry_to_html(entry))
        self.output.ensureCursorVisible()
        return entry

    def append_info(self, text: str, **kwargs) -> LogConsoleEntry:
        return self.append_message(text, level="info", **kwargs)

    def append_error(self, text: str, **kwargs) -> LogConsoleEntry:
        return self.append_message(text, level="error", **kwargs)

    def append_status(self, text: str, **kwargs) -> LogConsoleEntry:
        return self.append_message(text, level="status", **kwargs)

    def append_entry(self, entry: LogConsoleEntry) -> LogConsoleEntry:
        return self.append_message(
            entry.text,
            level=entry.level,
            color=entry.color,
            bold=entry.bold,
            italic=entry.italic,
            metadata=entry.metadata,
        )

    def set_entries(self, entries: list[LogConsoleEntry]) -> None:
        self._entries = list(entries)[-self._max_entries :]
        self._rebuild()

    def _rebuild(self) -> None:
        self.output.blockSignals(True)
        self.output.clear()
        for entry in self._entries:
            self.output.append(self._entry_to_html(entry))
        self.output.ensureCursorVisible()
        self.output.blockSignals(False)

    def _normalize_level(self, level: str) -> str:
        return level if level in {"info", "error", "status"} else "info"

    def _normalize_color(self, color: str | QColor | None) -> str | None:
        if color is None:
            return None
        if isinstance(color, QColor):
            return color.name(QColor.NameFormat.HexArgb)
        value = str(color).strip()
        return value or None

    def _entry_to_html(self, entry: LogConsoleEntry) -> str:
        classes = entry.level
        styles: list[str] = []
        if entry.color:
            styles.append(f"color: {entry.color}")
        if entry.bold:
            styles.append("font-weight: bold")
        if entry.italic:
            styles.append("font-style: italic")
        style_attr = f' style="{"; ".join(styles)}"' if styles else ""
        return f'<span class="{classes}"{style_attr}>{html.escape(entry.text)}</span>'

    def _apply_styles(self) -> None:
        info_color = self.theme_manager.get_color("dialog.text").name()
        bg_color = self.theme_manager.get_color("dialog.background").name()
        error_color = "#D70000" if self.theme_manager.is_dark() else "#FF0000"
        status_color = "#9E9E9E"

        self.output.setStyleSheet(f"""
            QTextEdit#LogConsoleOutput {{
                background: {bg_color};
                border: none;
                border-radius: 8px;
            }}
        """)

        stylesheet = f"""
        body {{ color: {info_color}; }}
        .info {{ color: {info_color}; }}
        .error {{ color: {error_color}; font-weight: bold; }}
        .status {{ color: {status_color}; }}
        """
        self.output.document().setDefaultStyleSheet(stylesheet)
        self.output.style().unpolish(self.output)
        self.output.style().polish(self.output)
        self.output.update()
        self._rebuild()
