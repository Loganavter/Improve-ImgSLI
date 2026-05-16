from __future__ import annotations

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QWheelEvent
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.i18n import tr
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.day_button import CalendarDayButton
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.models import (
    CalendarViewModel,
)

class CalendarWidget(QWidget):
    """Generic three-level calendar (days / months / years).

    Feed data via ``update_view(CalendarViewModel)``.
    Connect to signals for navigation and selection.
    """

    date_clicked = pyqtSignal(QDate)
    date_context_menu = pyqtSignal(QDate)
    month_selected = pyqtSignal(int, int)
    month_context_menu = pyqtSignal(int, int)
    year_selected = pyqtSignal(int)
    year_context_menu = pyqtSignal(int)

    navigate_previous = pyqtSignal()
    navigate_next = pyqtSignal()
    title_clicked = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        weekday_labels: list[str] | None = None,
        accent_color: str = "#3A7AFE",
        hover_color: str = "#3A3A3A",
        text_color: str = "#F2F2F2",
        bg_color: str = "#191919",
        weekend_bg: str = "#1E1E1E",
        disabled_bg: str = "#2A1A1A",
    ):
        super().__init__(parent)
        self._current_year = QDate.currentDate().year()

        self._accent = accent_color
        self._hover = hover_color
        self._text = text_color
        self._bg = bg_color
        self._weekend_bg = weekend_bg
        self._disabled_bg = disabled_bg

        self._day_buttons: list[CalendarDayButton] = []
        self._day_labels: list[QLabel] = []
        self._month_buttons: list[QPushButton] = []
        self._month_labels: list[QLabel] = []
        self._year_buttons: list[QPushButton] = []
        self._year_labels: list[QLabel] = []
        self._weekday_labels_widgets: list[QLabel] = []

        self._weekday_names = weekday_labels or [
            tr("weekday_mon", default="Mon"),
            tr("weekday_tue", default="Tue"),
            tr("weekday_wed", default="Wed"),
            tr("weekday_thu", default="Thu"),
            tr("weekday_fri", default="Fri"),
            tr("weekday_sat", default="Sat"),
            tr("weekday_sun", default="Sun"),
        ]

        self._setup_ui()

    def _faded_color(self, factor: float = 0.6) -> str:
        bg = QColor(self._bg)
        txt = QColor(self._text)
        r = int(txt.red() * factor + bg.red() * (1 - factor))
        g = int(txt.green() * factor + bg.green() * (1 - factor))
        b = int(txt.blue() * factor + bg.blue() * (1 - factor))
        return QColor(r, g, b).name()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        header = QHBoxLayout()
        self.prev_button = QPushButton("<")
        self.title_button = QPushButton()
        self.next_button = QPushButton(">")

        faded = self._faded_color(0.8)
        self.title_button.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; "
            f"color: {faded}; font-weight: bold; font-size: 11pt; }}"
            f"QPushButton:hover {{ background: {self._hover}; }}"
        )
        for btn in (self.prev_button, self.next_button):
            btn.setFixedSize(28, 28)

        header.addWidget(self.prev_button)
        header.addWidget(self.title_button, 1)
        header.addWidget(self.next_button)
        root.addLayout(header)

        self.prev_button.clicked.connect(self.navigate_previous.emit)
        self.next_button.clicked.connect(self.navigate_next.emit)
        self.title_button.clicked.connect(self.title_clicked.emit)

        self._view_stack = QStackedWidget()
        self._day_view = self._create_day_view()
        self._month_view = self._create_month_view()
        self._year_view = self._create_year_view()
        self._view_stack.addWidget(self._day_view)
        self._view_stack.addWidget(self._month_view)
        self._view_stack.addWidget(self._year_view)
        root.addWidget(self._view_stack, 1)

    def _create_day_view(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(5)

        faded = self._faded_color(0.6)
        widget.setStyleSheet(
            f'QPushButton[day-button="true"] {{'
            f"  border: 1px solid transparent; border-radius: 4px;"
            f"  padding: 5px; background: transparent;"
            f"}}"
            f'QPushButton[day-button="true"][weekend="true"][checked="false"][disabled_for_export="false"] {{'
            f"  background: {self._weekend_bg};"
            f"}}"
            f'QPushButton[day-button="true"][active="true"][checked="false"][disabled_for_export="false"]:hover {{'
            f"  background: {self._hover};"
            f"}}"
            f'QPushButton[day-button="true"][disabled_for_export="false"]:checked {{'
            f"  background: {self._accent};"
            f"}}"
            f'QPushButton[day-button="true"][disabled_for_export="true"] {{'
            f"  background: {self._disabled_bg};"
            f"}}"
            f'QLabel[day-label="true"] {{'
            f"  background: transparent; font-size: 11pt; color: {faded};"
            f"}}"
            f'QLabel[day-label="true"][active="true"] {{'
            f"  font-weight: 500; color: {self._text};"
            f"}}"
            f'QLabel[day-label="true"][checked="true"][disabled_for_export="false"] {{'
            f"  color: white; font-weight: 500;"
            f"}}"
            f'QLabel[weekday="true"] {{'
            f"  font-weight: bold; color: {self._text};"
            f"}}"
        )

        weekday_grid = QGridLayout()
        for i, name in enumerate(self._weekday_names):
            lbl = QLabel(name)
            lbl.setProperty("weekday", True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            weekday_grid.addWidget(lbl, 0, i)
            self._weekday_labels_widgets.append(lbl)
        layout.addLayout(weekday_grid)

        days_grid = QGridLayout()
        days_grid.setSpacing(2)
        for i in range(42):
            btn = CalendarDayButton()
            btn.date_clicked.connect(self.date_clicked.emit)
            btn.date_context_menu.connect(self.date_context_menu.emit)
            self._day_buttons.append(btn)

            lbl = QLabel()
            lbl.setProperty("day-label", True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._day_labels.append(lbl)

            days_grid.addWidget(btn, i // 7, i % 7)
            days_grid.addWidget(lbl, i // 7, i % 7)
        layout.addLayout(days_grid)
        return widget

    def _create_month_view(self) -> QWidget:
        widget = QWidget()
        grid = QGridLayout(widget)
        grid.setSpacing(5)
        for i in range(12):
            btn = QPushButton()
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            btn.clicked.connect(lambda _=False, m=i + 1: self.month_selected.emit(self._current_year, m))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, m=i + 1: self.month_context_menu.emit(self._current_year, m)
            )
            self._month_buttons.append(btn)

            lbl = QLabel()
            lbl.setProperty("month-label", True)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._month_labels.append(lbl)

            grid.addWidget(btn, i // 3, i % 3)
            grid.addWidget(lbl, i // 3, i % 3)
        for row in range(4):
            grid.setRowStretch(row, 1)
        return widget

    def _create_year_view(self) -> QWidget:
        widget = QWidget()
        widget.setLayout(QGridLayout())
        widget.layout().setSpacing(5)
        return widget

    def update_view(self, vm: CalendarViewModel) -> None:
        self.title_button.setText(vm.navigation_title)
        self.prev_button.setEnabled(vm.can_go_previous)
        self.next_button.setEnabled(vm.can_go_next)
        self._current_year = vm.current_year

        if vm.view_mode == "days":
            self._view_stack.setCurrentWidget(self._day_view)
            self._update_day_view(vm)
        elif vm.view_mode == "months":
            self._view_stack.setCurrentWidget(self._month_view)
            self._update_month_view(vm)
        elif vm.view_mode == "years":
            self._view_stack.setCurrentWidget(self._year_view)
            self._update_year_view(vm)

    def _update_day_view(self, vm: CalendarViewModel) -> None:
        sub_color = self._faded_color(0.5)

        for i, day in enumerate(vm.days):
            if i >= len(self._day_buttons):
                break
            btn = self._day_buttons[i]
            lbl = self._day_labels[i]

            if not day.is_in_current_month:
                btn.hide()
                lbl.hide()
                continue
            btn.show()
            lbl.show()

            is_weekend = day.date.dayOfWeek() >= 6
            btn.set_date(day.date)
            btn.setProperty("weekend", is_weekend)
            btn.setProperty("disabled_for_export", day.is_disabled)
            btn.setProperty("active", day.is_available)
            btn.setProperty("checked", day.is_selected)
            lbl.setProperty("active", day.is_available)
            lbl.setProperty("checked", day.is_selected)
            lbl.setProperty("disabled_for_export", day.is_disabled)

            btn.setEnabled(day.is_available)
            btn.setCursor(
                Qt.CursorShape.PointingHandCursor if day.is_available else Qt.CursorShape.ArrowCursor
            )

            num = str(day.date.day())
            sel_color = "white" if day.is_selected and not day.is_disabled else sub_color
            if day.is_available:
                html = (
                    f'<p style="line-height:1.0;margin:0;padding:0;">{num}<br>'
                    f'<span style="font-size:7pt;color:{sel_color};">{day.message_count}</span></p>'
                )
            else:
                html = f'<p style="line-height:1.0;margin:0;padding:0;">{num}</p>'

            if day.is_disabled:
                html = f"<span style='text-decoration:line-through;font-style:italic;'>{html}</span>"

            lbl.setText(html)
            btn.blockSignals(True)
            btn.setChecked(day.is_selected)
            btn.blockSignals(False)

            btn.style().unpolish(btn)
            btn.style().polish(btn)
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

    def _update_month_view(self, vm: CalendarViewModel) -> None:
        sub_color = self._faded_color(0.5)
        for mi in vm.months:
            idx = mi.month - 1
            if idx >= len(self._month_buttons):
                continue
            btn = self._month_buttons[idx]
            lbl = self._month_labels[idx]
            btn.setEnabled(mi.is_available)
            btn.setCursor(
                Qt.CursorShape.PointingHandCursor if mi.is_available else Qt.CursorShape.ArrowCursor
            )
            html = (
                f'<p style="line-height:1.0;margin:0;padding:0;text-align:center;">'
                f'{mi.name}<br><span style="font-size:9pt;color:{sub_color};">'
                f'{mi.message_count}</span></p>'
            )
            if mi.is_disabled:
                html = f"<span style='text-decoration:line-through;font-style:italic;'>{html}</span>"
            lbl.setText(html)

    def _update_year_view(self, vm: CalendarViewModel) -> None:
        layout = self._year_view.layout()
        while item := layout.takeAt(0):
            if w := item.widget():
                w.deleteLater()

        self._year_buttons.clear()
        self._year_labels.clear()
        sub_color = self._faded_color(0.5)

        row, col = 0, 0
        for yi in vm.years:
            btn = QPushButton()
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            btn.clicked.connect(lambda _=False, y=yi.year: self.year_selected.emit(y))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, y=yi.year: self.year_context_menu.emit(y)
            )
            self._year_buttons.append(btn)

            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._year_labels.append(lbl)

            layout.addWidget(btn, row, col)
            layout.addWidget(lbl, row, col)

            html = (
                f'<p style="line-height:1.0;margin:0;padding:0;text-align:center;">'
                f'{yi.name}<br><span style="font-size:9pt;color:{sub_color};">'
                f'{yi.message_count}</span></p>'
            )
            if yi.is_disabled:
                html = f"<span style='text-decoration:line-through;font-style:italic;'>{html}</span>"
            lbl.setText(html)

            btn.setEnabled(yi.is_available)
            col += 1
            if col > 2:
                col = 0
                row += 1
        layout.setRowStretch(row + 1, 1)

    def set_weekday_labels(self, names: list[str]) -> None:
        self._weekday_names = names
        for i, lbl in enumerate(self._weekday_labels_widgets):
            if i < len(names):
                lbl.setText(names[i])

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta > 0:
            self.navigate_previous.emit()
        elif delta < 0:
            self.navigate_next.emit()
        event.accept()
