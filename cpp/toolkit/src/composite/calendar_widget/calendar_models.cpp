#include "sli/toolkit/composite/calendar_widget/calendar_models.h"

#include <QDate>

namespace sli::toolkit {

namespace {

const QString kMonthNames[12] = {
    QStringLiteral("January"),   QStringLiteral("February"),
    QStringLiteral("March"),     QStringLiteral("April"),
    QStringLiteral("May"),       QStringLiteral("June"),
    QStringLiteral("July"),      QStringLiteral("August"),
    QStringLiteral("September"), QStringLiteral("October"),
    QStringLiteral("November"),  QStringLiteral("December"),
};

}  // namespace

CalendarViewModel buildDefaultViewModel(int year, int month, int day) {
  QDate first(year, month, 1);
  // QDate::dayOfWeek: Monday=1 … Sunday=7 → leading blanks before day 1.
  int leading_blanks = first.dayOfWeek() - 1;
  QDate grid_start = first.addDays(-leading_blanks);

  std::vector<CalendarDayInfo> days;
  days.reserve(42);
  for (int i = 0; i < 42; ++i) {
    QDate d = grid_start.addDays(i);
    bool in_month = (d.month() == month && d.year() == year);
    CalendarDayInfo info;
    info.date = d;
    info.message_count = QString();
    info.is_available = in_month;
    info.is_disabled = false;
    info.is_selected = (in_month && d.day() == day);
    info.is_in_current_month = in_month;
    days.push_back(std::move(info));
  }

  QString title =
      QStringLiteral("%1 %2").arg(kMonthNames[month - 1]).arg(year);

  CalendarViewModel vm;
  vm.current_year = year;
  vm.current_month = month;
  vm.current_day = day;
  vm.view_mode = QStringLiteral("days");
  vm.days = std::move(days);
  vm.navigation_title = title;
  return vm;
}

}  // namespace sli::toolkit
