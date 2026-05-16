from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QDate

@dataclass
class CalendarDayInfo:
    date: QDate
    message_count: str = ""
    is_available: bool = False
    is_disabled: bool = False
    is_selected: bool = False
    is_in_current_month: bool = True

@dataclass
class CalendarMonthInfo:
    year: int
    month: int
    name: str
    message_count: str = ""
    is_available: bool = False
    is_disabled: bool = False

@dataclass
class CalendarYearInfo:
    year: int
    name: str
    message_count: str = ""
    is_available: bool = False
    is_disabled: bool = False

@dataclass
class CalendarViewModel:
    current_year: int
    current_month: int
    current_day: int = 1

    view_mode: str = "days"

    days: list[CalendarDayInfo] = field(default_factory=list)
    months: list[CalendarMonthInfo] = field(default_factory=list)
    years: list[CalendarYearInfo] = field(default_factory=list)

    can_go_previous: bool = True
    can_go_next: bool = True
    navigation_title: str = ""

    def get_current_date(self) -> QDate:
        return QDate(self.current_year, self.current_month, self.current_day)
