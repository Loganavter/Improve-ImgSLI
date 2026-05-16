from __future__ import annotations

import html
import os

from PyQt6.QtCore import QProcess, Qt, pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QTextEdit, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.custom_button import CustomButton
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar

class ProcessConsoleWidget(QWidget):
    outputReceived = pyqtSignal(str)
    errorReceived = pyqtSignal(str)
    commandSubmitted = pyqtSignal(str)
    processStarted = pyqtSignal()
    processFinished = pyqtSignal(int, int)
    processStateChanged = pyqtSignal(int)

    def __init__(self, parent=None, *, max_entries: int = 2000):
        super().__init__(parent)
        self._max_entries = max(1, int(max_entries))
        self._entries: list[tuple[str, str]] = []
        self.theme_manager = ThemeManager.get_instance()
        self.process = QProcess(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.output = QTextEdit(self)
        self.output.setObjectName("ProcessConsoleOutput")
        self.output.setReadOnly(True)
        self.output.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.output.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        fixed_font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self.output.setFont(fixed_font)

        scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self.output)
        self.output.setVerticalScrollBar(scrollbar)
        self.output.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.input_row = QWidget(self)
        input_layout = QHBoxLayout(self.input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(8)

        self.input_edit = QLineEdit(self.input_row)
        self.input_edit.setObjectName("ProcessConsoleInput")
        self.input_edit.setPlaceholderText("Enter command")
        self.input_edit.setFont(fixed_font)

        self.send_button = CustomButton(None, "Send", self.input_row)
        self.send_button.clicked.connect(self.submit_current_input)
        self.input_edit.returnPressed.connect(self.submit_current_input)

        input_layout.addWidget(self.input_edit, 1)
        input_layout.addWidget(self.send_button)

        layout.addWidget(self.output, 1)
        layout.addWidget(self.input_row)

        self.process.readyReadStandardOutput.connect(self._on_stdout_ready)
        self.process.readyReadStandardError.connect(self._on_stderr_ready)
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.stateChanged.connect(self._on_state_changed)

        self.theme_manager.theme_changed.connect(self._apply_styles)
        self._apply_styles()

    def set_max_entries(self, max_entries: int) -> None:
        self._max_entries = max(1, int(max_entries))
        self._entries = self._entries[-self._max_entries :]
        self._rebuild()

    def clear_output(self) -> None:
        self._entries.clear()
        self.output.clear()

    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start_process(
        self,
        program: str,
        args: list[str] | None = None,
        *,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if self.is_running():
            self.stop_process(force=True)

        self.clear_output()
        self.process.setProgram(program)
        self.process.setArguments(list(args or []))
        if workdir:
            self.process.setWorkingDirectory(workdir)
        if env:
            process_env = self.process.processEnvironment()
            for key, value in env.items():
                process_env.insert(str(key), str(value))
            self.process.setProcessEnvironment(process_env)
        self.process.start()

    def start_shell(self, *, workdir: str | None = None) -> None:
        if os.name == "nt":
            self.start_process("cmd.exe", workdir=workdir)
            return
        shell = os.environ.get("SHELL") or "/bin/bash"
        args = ["-i"] if os.path.basename(shell) in {"bash", "zsh", "sh"} else []
        self.start_process(shell, args, workdir=workdir)

    def send_input(self, text: str, *, add_newline: bool = True, echo: bool = True) -> None:
        if not self.is_running():
            return
        payload = str(text)
        if echo and payload:
            self._append_entry("command", f"> {payload}")
        if add_newline:
            payload += "\n"
        self.process.write(payload.encode("utf-8", errors="replace"))
        self.commandSubmitted.emit(str(text))

    def submit_current_input(self) -> None:
        text = self.input_edit.text().strip()
        if not text:
            return
        self.send_input(text)
        self.input_edit.clear()

    def stop_process(self, *, force: bool = False) -> None:
        if not self.is_running():
            return
        if force:
            self.process.kill()
        else:
            self.process.terminate()

    def _append_entry(self, level: str, text: str) -> None:
        safe_level = (
            level if level in {"info", "error", "status", "command"} else "info"
        )
        message = str(text)
        self._entries.append((safe_level, message))
        self._entries = self._entries[-self._max_entries :]
        self.output.append(
            f'<span class="{safe_level}">{html.escape(message)}</span>'
        )
        self.output.ensureCursorVisible()

    def _rebuild(self) -> None:
        self.output.blockSignals(True)
        self.output.clear()
        for level, message in self._entries:
            self.output.append(
                f'<span class="{level}">{html.escape(message)}</span>'
            )
        self.output.ensureCursorVisible()
        self.output.blockSignals(False)

    def _on_stdout_ready(self) -> None:
        text = bytes(self.process.readAllStandardOutput()).decode(
            "utf-8", errors="replace"
        )
        if not text:
            return
        for line in text.splitlines():
            self._append_entry("info", line)
        if text.endswith("\n") is False and text.strip():
            trailing = text.splitlines()[-1] if text.splitlines() else text
            if trailing and not text.endswith("\n"):
                pass
        self.outputReceived.emit(text)

    def _on_stderr_ready(self) -> None:
        text = bytes(self.process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )
        if not text:
            return
        for line in text.splitlines():
            self._append_entry("error", line)
        self.errorReceived.emit(text)

    def _on_started(self) -> None:
        self._append_entry("status", "Process started")
        self.processStarted.emit()

    def _on_finished(self, exit_code: int, exit_status) -> None:
        self._append_entry(
            "status",
            f"Process finished with exit code {exit_code}",
        )
        self.processFinished.emit(exit_code, int(exit_status))

    def _on_state_changed(self, state) -> None:
        self.processStateChanged.emit(int(state))

    def _apply_styles(self) -> None:
        info_color = self.theme_manager.get_color("dialog.text").name()
        error_color = "#D70000" if self.theme_manager.is_dark() else "#FF0000"
        status_color = "#9E9E9E"
        command_color = self.theme_manager.get_color("accent").name()

        stylesheet = f"""
        body {{ color: {info_color}; }}
        .info {{ color: {info_color}; }}
        .error {{ color: {error_color}; font-weight: bold; }}
        .status {{ color: {status_color}; }}
        .command {{ color: {command_color}; font-weight: bold; }}
        """
        self.output.document().setDefaultStyleSheet(stylesheet)
        self.output.style().unpolish(self.output)
        self.output.style().polish(self.output)
        self.output.update()
