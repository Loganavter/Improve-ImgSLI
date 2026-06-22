#pragma once

#include <QDate>
#include <QString>

#include <string>
#include <vector>

namespace sli::toolkit {

struct CalendarDayInfo {
  QDate date;
  QString message_count;
  bool is_available = false;
  bool is_disabled = false;
  bool is_selected = false;
  bool is_in_current_month = true;
};

struct CalendarMonthInfo {
  int year = 0;
  int month = 0;
  QString name;
  QString message_count;
  bool is_available = false;
  bool is_disabled = false;
};

struct CalendarYearInfo {
  int year = 0;
  QString name;
  QString message_count;
  bool is_available = false;
  bool is_disabled = false;
};

struct CalendarViewModel {
  int current_year = 0;
  int current_month = 0;
  int current_day = 1;

  QString view_mode = QStringLiteral("days");

  std::vector<CalendarDayInfo> days;
  std::vector<CalendarMonthInfo> months;
  std::vector<CalendarYearInfo> years;

  bool can_go_previous = true;
  bool can_go_next = true;
  QString navigation_title;

  QDate getCurrentDate() const {
    return QDate(current_year, current_month, current_day);
  }
};

/// Build a zero-config view-model that fills 6x7 days for the given month.
/// All days in the current month are available; padding days from neighbouring
/// months are present but flagged is_in_current_month=false so the widget
/// hides them.
CalendarViewModel buildDefaultViewModel(int year, int month, int day = 1);

}  // namespace sli::toolkit
