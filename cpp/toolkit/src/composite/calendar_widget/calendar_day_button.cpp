#include "sli/toolkit/composite/calendar_widget/calendar_day_button.h"

#include <QCursor>
#include <QMouseEvent>
#include <QSizePolicy>

#include "sli/toolkit/buttons/content/button_row.h"
#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/buttons/specs.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

CalendarDayButton::CalendarDayButton(QWidget* parent)
    : Button(Button::Config{
          .variant = Button::Variant::Ghost,
          .toggle = true,
          .size = QSize(0, 0),
          .cornerRadius = 4,
      },
      parent) {
  setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
  setMinimumSize(28, 36);
  setFocusPolicy(Qt::NoFocus);
  setAttribute(Qt::WA_MacShowFocusRect, false);
  setContextMenuPolicy(Qt::CustomContextMenu);

  connect(this, &QAbstractButton::clicked, this,
          &CalendarDayButton::onButtonClicked);
  connect(this, &QWidget::customContextMenuRequested, this,
          &CalendarDayButton::onContextMenu);

  // Initial spec build with empty row
  buttons::ButtonRow empty_row;
  current_rows_ = {empty_row};
  rebuildSpec();
}

void CalendarDayButton::setRows(const std::vector<buttons::ButtonRow>& rows,
                                 bool compact) {
  current_rows_ = rows;
  current_compact_ = compact;
  rebuildSpec();
}

void CalendarDayButton::setData(bool has_data, const QColor& color) {
  has_data_ = has_data;
  data_color_ = color;
  rebuildSpec();
}

void CalendarDayButton::setDate(const QDate& date) { date_ = date; }

void CalendarDayButton::setWeekend(bool is_weekend, const QColor& color) {
  is_weekend_ = is_weekend;
  weekend_color_ = color;
  rebuildSpec();
}

void CalendarDayButton::setDisabledExport(bool is_disabled,
                                          const QColor& color) {
  is_disabled_export_ = is_disabled;
  disabled_export_color_ = color;
  rebuildSpec();
}

void CalendarDayButton::rebuildSpec() {
  using namespace buttons;

  ButtonRegion region;
  region.id = QStringLiteral("_main");
  region.rows = current_rows_;
  region.toggle = true;

  // Resolve background based on current calendar state (mirrors Python's
  // _sync_calendar_background)
  if (is_disabled_export_ && disabled_export_color_.isValid()) {
    region.overrideBgColor = disabled_export_color_;
  } else if (isChecked()) {
    region.overrideBgColor = Theme::getColor(QStringLiteral("accent"));
  } else if (is_weekend_ && weekend_color_.isValid()) {
    region.customBgColor = weekend_color_;
  } else if (has_data_ && data_color_.isValid()) {
    region.customBgColor = data_color_;
  } else {
    // No background overrides
  }

  ButtonSpecArgs args;
  args.shape = ShapeSpec{};
  args.shape->cornerRadius = 4;
  args.variant = QStringLiteral("ghost");
  args.density = QStringLiteral("normal");

  ButtonSpec s = ButtonSpec::fromRegions({region}, args);
  setSpec(s);
  update();
}

void CalendarDayButton::onButtonClicked() {
  if (date_.isValid()) {
    emit dateClicked(date_);
  }
}

void CalendarDayButton::onContextMenu(const QPoint& /*pos*/) {
  if (date_.isValid()) {
    emit dateContextMenu(date_);
  }
}

}  // namespace sli::toolkit