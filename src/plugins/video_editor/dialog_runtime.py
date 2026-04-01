import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QKeySequence, QPixmap, QPalette
from PyQt6.QtWidgets import QLineEdit

from shared_toolkit.ui.widgets.atomic.custom_line_edit import CustomLineEdit

logger = logging.getLogger("ImproveImgSLI")

class VideoEditorDialogRuntime:
    def __init__(self, dialog):
        self.dialog = dialog

    def connect_presenter_signals(self):
        d = self.dialog
        d.presenter.previewUpdated.connect(d._on_preview_updated)
        d.presenter.previewReady.connect(d._emit_ready_to_show)
        d.presenter.timelinePositionChanged.connect(d._on_timeline_position_changed)
        d.presenter.playbackStateChanged.connect(d._on_playback_state_changed)
        d.presenter.buttonsStateChanged.connect(d._on_buttons_state_changed)
        d.presenter.thumbnailsUpdated.connect(d._on_thumbnails_updated)
        d.presenter.exportStarted.connect(d._on_export_started)
        d.presenter.exportLog.connect(d._on_export_log)
        d.presenter.errorOccurred.connect(d._on_error_occurred)

    def update_settings_panel_width(self):
        d = self.dialog
        try:
            d.settings_panel.ensurePolished()
            max_tab_content_width = 0
            for i in range(d.tabs.count()):
                widget = d.tabs.widget(i)
                if widget:
                    widget.ensurePolished()
                    widget.adjustSize()
                    max_tab_content_width = max(
                        max_tab_content_width, widget.sizeHint().width()
                    )
            tab_bar_width = d.tabs.tabBar().sizeHint().width()
            d.btn_export.ensurePolished()
            d.btn_export.adjustSize()
            btn_width = d.btn_export.sizeHint().width()
            optimal_width = max(350, max_tab_content_width + 44, tab_bar_width + 44, btn_width + 24)
            d.settings_panel.setFixedWidth(int(min(optimal_width, 650)))
        except Exception as exc:
            logger.warning(f"Error calculating panel width: {exc}")
            d.settings_panel.setFixedWidth(380)

    def set_focus_policies(self):
        d = self.dialog
        for btn in [
            d.btn_undo,
            d.btn_redo,
            d.btn_trim,
            d.btn_play,
            d.btn_export,
            d.btn_lock_ratio,
            d.btn_fit_content,
            d.btn_fit_fill_color,
        ]:
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if hasattr(d, "btn_stop_export"):
            d.btn_stop_export.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        d.timeline.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def position_stop_export_button(self):
        d = self.dialog
        if not hasattr(d, "btn_export") or not hasattr(d, "btn_stop_export"):
            return
        x = 12
        y = max(0, (d.btn_export.height() - d.btn_stop_export.height()) // 2)
        d.btn_stop_export.move(x, y)
        d.btn_stop_export.raise_()

    def setup_shortcuts(self):
        d = self.dialog

        def handle_space():
            focused = d.focusWidget()
            if not isinstance(focused, (QLineEdit, CustomLineEdit)):
                d._on_play_toggled(not d.btn_play.isChecked())

        from PyQt6.QtGui import QShortcut

        d.shortcut_space = QShortcut(QKeySequence(Qt.Key.Key_Space), d)
        d.shortcut_space.activated.connect(handle_space)
        d.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), d)
        d.shortcut_undo.activated.connect(d._on_undo_clicked)
        d.shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), d)
        d.shortcut_redo.activated.connect(d._on_redo_clicked)
        d.shortcut_redo_alt = QShortcut(QKeySequence("Ctrl+Shift+Z"), d)
        d.shortcut_redo_alt.activated.connect(d._on_redo_clicked)

        def handle_delete():
            focused = d.focusWidget()
            if not isinstance(focused, (QLineEdit, CustomLineEdit)):
                d._on_trim_clicked()

        d.shortcut_delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), d)
        d.shortcut_delete.activated.connect(handle_delete)
        d.shortcut_backspace = QShortcut(QKeySequence(Qt.Key.Key_Backspace), d)
        d.shortcut_backspace.activated.connect(handle_delete)

    def set_preview_image(self, pixmap: QPixmap):
        d = self.dialog
        if not pixmap:
            logger.warning("[set_preview_image] Received None pixmap!")
            return
        if hasattr(d.preview_label, "set_pixmap"):
            d.preview_label.set_pixmap(pixmap)
            return
        label_w = d.preview_label.width()
        label_h = d.preview_label.height()
        pix_w = pixmap.width()
        pix_h = pixmap.height()
        if label_w > 0 and label_h > 0 and (abs(pix_w - label_w) > 10 or abs(pix_h - label_h) > 10):
            d.preview_label.setPixmap(
                pixmap.scaled(
                    label_w,
                    label_h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            return
        d.preview_label.setPixmap(pixmap)

    def update_preview_palette(self):
        bg = QColor("#0a0a0a") if self.dialog.theme_manager.is_dark() else QColor("#f5f5f5")
        pal = self.dialog.preview_label.palette()
        pal.setColor(QPalette.ColorRole.Window, bg)
        self.dialog.preview_label.setPalette(pal)
        self.dialog.preview_label.update()

    def apply_style(self):
        self.dialog.theme_manager.apply_theme_to_dialog(self.dialog)

    def emit_ready_to_show(self):
        d = self.dialog
        if d._ready_to_show_emitted:
            return
        d._ready_to_show_emitted = True
        d.readyToShow.emit()

    def set_export_progress(self, value: int):
        d = self.dialog
        if not d.export_progress.isVisible():
            d.export_progress.setVisible(True)
            d.btn_export.set_override_bg_color(
                QColor(d.theme_manager.get_color("button.primary.background"))
            )
            d.btn_export.setCursor(Qt.CursorShape.ArrowCursor)
            d.btn_export.setText(d._tr("video.rendering"))
            d.btn_stop_export.show()
            self.position_stop_export_button()
        d.export_progress.setValue(value)

    def reset_export_ui_state(self):
        d = self.dialog
        d.export_progress.setVisible(False)
        d.export_progress.setValue(0)
        d.btn_export.set_override_bg_color(None)
        d.btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        d.btn_export.setText(d._tr("action.export_video"))
        if hasattr(d, "btn_stop_export"):
            d.btn_stop_export.hide()
        d._set_export_progress_state("active")

    def on_export_finished(self, success: bool):
        d = self.dialog
        if hasattr(d, "export_log_edit"):
            from datetime import datetime
            ts = datetime.now().strftime("%H:%M:%S")
            if success:
                d.export_log_edit.appendPlainText(f"── Export finished {ts} ──")
            else:
                d.export_log_edit.appendPlainText(f"── Export failed {ts} ──")
        if success:
            d.export_progress.setValue(100)
            d._set_export_progress_state("success")
            d.btn_export.setText(d._tr("video.done"))
            QTimer.singleShot(2000, self.reset_export_ui_state)
            return
        self.reset_export_ui_state()
        if hasattr(d, "tabs") and hasattr(d, "tab_log"):
            d.tabs.setCurrentWidget(d.tab_log)
