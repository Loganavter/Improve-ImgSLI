#include "sli/toolkit/composite/calendar_widget/calendar_widget.h"

#include <QDate>
#include <QGridLayout>
#include <QHBoxLayout>
#include <QLabel>
#include <QResizeEvent>
#include <QSizePolicy>
#include <QStackedWidget>
#include <QVBoxLayout>
#include <QWheelEvent>

#include <algorithm>
#include <cmath>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/content/button_row.h"
#include "sli/toolkit/buttons/specs.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit {

// ============================================================================
// Static helpers
// ============================================================================

QColor CalendarWidget::mixColors(const QColor& first, const QColor& second,
                                 double first_weight) {
  first_weight = std::max(0.0, std::min(1.0, first_weight));
  double second_weight = 1.0 - first_weight;
  return QColor(
      static_cast<int>(first.red() * first_weight + second.red() * second_weight),
      static_cast<int>(first.green() * first_weight + second.green() * second_weight),
      static_cast<int>(first.blue() * first_weight + second.blue() * second_weight));
}

QColor CalendarWidget::contrastColor(const QColor& color) {
  double luminance =
      0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue();
  return (luminance > 150) ? QColor(QStringLiteral("#111111"))
                           : QColor(QStringLiteral("#F5F5F5"));
}

QColor CalendarWidget::fadedColor(double factor) const {
  const QColor& bg = palette_.bg;
  const QColor& txt = palette_.text;
  int r = static_cast<int>(txt.red() * factor + bg.red() * (1.0 - factor));
  int g = static_cast<int>(txt.green() * factor + bg.green() * (1.0 - factor));
  int b = static_cast<int>(txt.blue() * factor + bg.blue() * (1.0 - factor));
  return QColor(r, g, b);
}

std::vector<QString> CalendarWidget::defaultWeekdayLabels() {
  return {QStringLiteral("Mon"), QStringLiteral("Tue"), QStringLiteral("Wed"),
          QStringLiteral("Thu"), QStringLiteral("Fri"), QStringLiteral("Sat"),
          QStringLiteral("Sun")};
}

// ============================================================================
// Constructor
// ============================================================================

CalendarWidget::CalendarWidget(
    QWidget* parent, const std::vector<QString>& weekday_labels,
    const std::optional<QColor>& accent_color,
    const std::optional<QColor>& hover_color,
    const std::optional<QColor>& text_color,
    const std::optional<QColor>& bg_color,
    const std::optional<QColor>& data_bg,
    const std::optional<QColor>& weekend_bg,
    const std::optional<QColor>& disabled_bg)
    : QWidget(parent) {
  current_year_ = QDate::currentDate().year();

  color_overrides_.accent = accent_color;
  color_overrides_.hover = hover_color;
  color_overrides_.text = text_color;
  color_overrides_.bg = bg_color;
  color_overrides_.data_bg = data_bg;
  color_overrides_.weekend_bg = weekend_bg;
  color_overrides_.disabled_bg = disabled_bg;

  weekday_names_ = weekday_labels.empty() ? defaultWeekdayLabels()
                                          : weekday_labels;

  resolvePalette();
  setupUi();
  applyStyles();

  // Theme change callback (mirrors Python's
  // self._theme_manager.theme_changed.connect(self._on_theme_changed))
  Theme::onThemeChanged(this, [this] { onThemeChanged(); });
}

// ============================================================================
// Palette resolution
// ============================================================================

void CalendarWidget::resolvePalette() {
  auto defaultColor = [](const QString& token, const QString& fallback) {
    return Theme::getColor(token);
  };

  QColor bg =
      Theme::getColor(QStringLiteral("dialog.background"));
  if (!bg.isValid()) bg = QColor(QStringLiteral("#191919"));
  if (color_overrides_.bg) bg = *color_overrides_.bg;

  QColor text =
      Theme::getColor(QStringLiteral("dialog.text"));
  if (!text.isValid()) text = QColor(QStringLiteral("#F2F2F2"));
  if (color_overrides_.text) text = *color_overrides_.text;

  QColor accent = Theme::getColor(QStringLiteral("accent"));
  if (!accent.isValid()) accent = QColor(QStringLiteral("#3A7AFE"));
  if (color_overrides_.accent) accent = *color_overrides_.accent;

  QColor checked = Theme::getColor(
      QStringLiteral("button.toggle.background.checked"));
  if (!checked.isValid()) checked = QColor(QStringLiteral("#C0C0C0"));

  bool is_dark = Theme::isDark();

  QColor hover = color_overrides_.hover.value_or(
      Theme::getColor(QStringLiteral("dialog.button.hover")));
  if (!hover.isValid()) hover = QColor(QStringLiteral("#3A3A3A"));

  palette_.accent = accent;
  palette_.hover = hover;
  palette_.text = text;
  palette_.bg = bg;

  palette_.weekend_bg = color_overrides_.weekend_bg.value_or(
      mixColors(accent, bg, is_dark ? 0.24 : 0.18));
  palette_.data_bg =
      color_overrides_.data_bg.value_or(checked);
  palette_.disabled_bg = color_overrides_.disabled_bg.value_or(
      is_dark ? mixColors(QColor(QStringLiteral("#E06C6C")), bg, 0.62)
              : mixColors(QColor(QStringLiteral("#D94F4F")), bg, 0.28));

  palette_.muted_text = fadedColor(0.68);
  palette_.data_text = contrastColor(palette_.data_bg);
  palette_.disabled_text = contrastColor(palette_.disabled_bg);
}

void CalendarWidget::setColors(std::optional<QColor> accent_color,
                               std::optional<QColor> hover_color,
                               std::optional<QColor> text_color,
                               std::optional<QColor> bg_color,
                               std::optional<QColor> data_bg,
                               std::optional<QColor> weekend_bg,
                               std::optional<QColor> disabled_bg) {
  auto assign = [](auto& field, const auto& val) {
    if (val.has_value())
      field = val;
    else
      field.reset();
  };
  assign(color_overrides_.accent, accent_color);
  assign(color_overrides_.hover, hover_color);
  assign(color_overrides_.text, text_color);
  assign(color_overrides_.bg, bg_color);
  assign(color_overrides_.data_bg, data_bg);
  assign(color_overrides_.weekend_bg, weekend_bg);
  assign(color_overrides_.disabled_bg, disabled_bg);

  resolvePalette();
  applyStyles();
}

void CalendarWidget::onThemeChanged() {
  resolvePalette();
  applyStyles();
}

// ============================================================================
// Dimension helpers
// ============================================================================

int CalendarWidget::fontUnit() const {
  return std::max(12, fontMetrics().height());
}

int CalendarWidget::spacingUnit() const {
  return std::max(2, fontUnit() / 3);
}

int CalendarWidget::navButtonSize() const {
  return std::max(28, static_cast<int>(fontUnit() * 1.8));
}

std::pair<int, int> CalendarWidget::monthYearRowSizes() const {
  int h = std::max(120, height());
  int title_px = std::max(11, h / 35);
  int sub_px = std::max(9, h / 45);
  return {title_px, sub_px};
}

// ============================================================================
// Input helpers
// ============================================================================

void CalendarWidget::setButtonAvailability(Button* btn, bool is_available) {
  btn->setEnabled(is_available);
  btn->setCursor(is_available ? QCursor(Qt::PointingHandCursor)
                              : QCursor(Qt::ArrowCursor));
}

void CalendarWidget::setPeriodDisabledExport(Button* btn, bool is_disabled) {
  // In C++, we rebuild the region to set overrideBgColor
  auto s = btn->spec();
  if (!s.regions.empty()) {
    if (is_disabled) {
      s.regions.front().style.overrideBgColor = palette_.disabled_bg;
    } else {
      s.regions.front().style.overrideBgColor.reset();
    }
    btn->setSpec(s);
    btn->update();
  }
}

// ============================================================================
// Row builders
// ============================================================================

std::vector<buttons::ButtonRow> CalendarWidget::periodRows(
    const QString& title, const QString& value, int title_px, int sub_px,
    const QColor& sub_color, bool strike,
    const std::optional<QColor>& title_color) const {
  using namespace buttons;

  ButtonRow title_row;
  title_row.text = title;
  title_row.size = title_px;
  title_row.weight = RowWeight::Bold;
  title_row.color = title_color.value_or(QColor());
  title_row.ratio = 0.6;
  title_row.strikethrough = strike;
  title_row.italic = strike;

  ButtonRow sub_row;
  sub_row.text = value;
  sub_row.size = sub_px;
  sub_row.color = sub_color;
  sub_row.ratio = 0.4;
  sub_row.strikethrough = strike;

  return {title_row, sub_row};
}

// ============================================================================
// UI Setup
// ============================================================================

void CalendarWidget::setupUi() {
  auto* root = new QVBoxLayout(this);
  root->setContentsMargins(0, 0, 0, 0);
  root->setSpacing(spacingUnit());

  // Header
  auto* header = new QHBoxLayout();
  int nav_h = navButtonSize();

  prev_button_ = new Button(Button::Config{
      .text = QStringLiteral("\u2039"),
      .variant = Button::Variant::Surface,
      .size = QSize(nav_h, nav_h),
      .cornerRadius = 4,
  }, this);

  title_button_ = new Button(Button::Config{
      .variant = Button::Variant::Surface,
      .size = QSize(0, nav_h),
      .cornerRadius = 4,
  }, this);
  title_button_->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
  title_button_->setText(QString());

  next_button_ = new Button(Button::Config{
      .text = QStringLiteral("\u203A"),
      .variant = Button::Variant::Surface,
      .size = QSize(nav_h, nav_h),
      .cornerRadius = 4,
  }, this);

  header->addWidget(prev_button_);
  header->addWidget(title_button_, 1);
  header->addWidget(next_button_);
  root->addLayout(header);

  connect(prev_button_, &Button::clicked, this,
          &CalendarWidget::navigatePrevious);
  connect(next_button_, &Button::clicked, this,
          &CalendarWidget::navigateNext);
  connect(title_button_, &Button::clicked, this,
          &CalendarWidget::titleClicked);

  // View stack
  view_stack_ = new QStackedWidget(this);
  day_view_ = createDayView();
  month_view_ = createMonthView();
  year_view_ = createYearView();
  view_stack_->addWidget(day_view_);
  view_stack_->addWidget(month_view_);
  view_stack_->addWidget(year_view_);
  root->addWidget(view_stack_, 1);

  applyStyles();
}

void CalendarWidget::applyStyles() {
  setStyleSheet(QStringLiteral("color: %1;").arg(palette_.text.name()));

  if (day_view_) {
    day_view_->setStyleSheet(
        QStringLiteral("QLabel[weekday=\"true\"] { font-weight: bold; color: %1; }")
            .arg(palette_.text.name()));
  }

  auto applyBtnColors = [this](Button* btn) {
    if (btn) {
      btn->setStyleSheet(QString());
      btn->update();
    }
  };

  applyBtnColors(prev_button_);
  applyBtnColors(title_button_);
  applyBtnColors(next_button_);

  for (auto* btn : month_buttons_) applyBtnColors(btn);
  for (auto* btn : year_buttons_) applyBtnColors(btn);
  for (auto* btn : day_buttons_) applyBtnColors(btn);

  if (last_vm_.has_value()) {
    updateView(*last_vm_);
  }
}

QWidget* CalendarWidget::createDayView() {
  auto* widget = new QWidget();
  auto* layout = new QVBoxLayout(widget);
  layout->setSpacing(spacingUnit());

  auto* weekday_grid = new QGridLayout();
  for (int i = 0; i < 7 && i < static_cast<int>(weekday_names_.size()); ++i) {
    auto* lbl = new QLabel(weekday_names_[i]);
    lbl->setProperty("weekday", true);
    lbl->setAlignment(Qt::AlignCenter);
    lbl->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);
    weekday_grid->addWidget(lbl, 0, i);
    weekday_label_widgets_.push_back(lbl);
  }
  layout->addLayout(weekday_grid);

  auto* days_grid = new QGridLayout();
  days_grid->setSpacing(std::max(1, spacingUnit() / 2));
  for (int i = 0; i < 42; ++i) {
    auto* btn = new CalendarDayButton(widget);
    connect(btn, &CalendarDayButton::dateClicked, this,
            &CalendarWidget::dateClicked);
    connect(btn, &CalendarDayButton::dateContextMenu, this,
            &CalendarWidget::dateContextMenu);
    day_buttons_.push_back(btn);
    days_grid->addWidget(btn, i / 7, i % 7);
  }
  layout->addLayout(days_grid);
  return widget;
}

QWidget* CalendarWidget::createMonthView() {
  auto* widget = new QWidget();
  auto* grid = new QGridLayout(widget);
  grid->setSpacing(spacingUnit());
  int min_w = std::max(50, fontUnit() * 4);
  int min_h = std::max(40, static_cast<int>(fontUnit() * 2.5));

  for (int i = 0; i < 12; ++i) {
    int month = i + 1;
    auto* btn = new Button(Button::Config{
        .variant = Button::Variant::Surface,
        .cornerRadius = 6,
    }, widget);
    btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    btn->setMinimumSize(min_w, min_h);

    connect(btn, &Button::clicked, this, [this, month]() {
      emit monthSelected(current_year_, month);
    });
    connect(btn, &Button::rightClicked, this, [this, month]() {
      emit monthContextMenu(current_year_, month);
    });

    month_buttons_.push_back(btn);
    grid->addWidget(btn, i / 3, i % 3);
  }
  for (int row = 0; row < 4; ++row) {
    grid->setRowStretch(row, 1);
  }
  return widget;
}

QWidget* CalendarWidget::createYearView() {
  auto* widget = new QWidget();
  widget->setLayout(new QGridLayout());
  widget->layout()->setSpacing(spacingUnit());
  return widget;
}

// ============================================================================
// updateView
// ============================================================================

void CalendarWidget::updateView(const CalendarViewModel& vm) {
  last_vm_ = vm;
  title_button_->setText(vm.navigation_title);
  setButtonAvailability(prev_button_, vm.can_go_previous);
  setButtonAvailability(next_button_, vm.can_go_next);
  current_year_ = vm.current_year;

  if (vm.view_mode == QStringLiteral("days")) {
    view_stack_->setCurrentWidget(day_view_);
    updateDayView(vm);
  } else if (vm.view_mode == QStringLiteral("months")) {
    view_stack_->setCurrentWidget(month_view_);
    updateMonthView(vm);
  } else if (vm.view_mode == QStringLiteral("years")) {
    view_stack_->setCurrentWidget(year_view_);
    updateYearView(vm);
  }
}

void CalendarWidget::updateDayView(const CalendarViewModel& vm) {
  int h = std::max(120, height());
  int num_px = std::max(11, h / 28);
  int sub_px = std::max(8, h / 42);

  for (size_t i = 0; i < vm.days.size() && i < day_buttons_.size(); ++i) {
    const auto& day = vm.days[i];
    auto* btn = day_buttons_[i];

    if (!day.is_in_current_month) {
      btn->hide();
      continue;
    }
    btn->show();

    bool is_weekend = day.date.dayOfWeek() >= 6;
    bool has_messages =
        !day.message_count.isEmpty() && day.message_count.toInt() > 0;

    btn->setDate(day.date);
    btn->setWeekend(is_weekend, palette_.weekend_bg);
    btn->setDisabledExport(day.is_disabled, palette_.disabled_bg);
    btn->setData(has_messages, palette_.data_bg);
    setButtonAvailability(btn, day.is_available);

    btn->blockSignals(true);
    btn->setChecked(day.is_selected);
    btn->blockSignals(false);

    QString num = QString::number(day.date.day());
    QColor num_color;
    QColor sub_text_color;

    if (day.is_selected && !day.is_disabled) {
      QColor selected_text = contrastColor(palette_.accent);
      num_color = selected_text;
      sub_text_color = selected_text;
    } else if (day.is_disabled) {
      num_color = palette_.disabled_text;
      sub_text_color = palette_.disabled_text;
    } else if (has_messages && day.is_available) {
      num_color = palette_.data_text;
      sub_text_color = palette_.data_text;
    } else {
      num_color = palette_.muted_text;
      sub_text_color = palette_.muted_text;
    }

    bool strike = day.is_disabled;

    using namespace buttons;
    std::vector<ButtonRow> rows;

    if (day.is_available) {
      // Ballast row on top: same height as count row, keeps number centered
      ButtonRow ballast;
      ballast.text = day.message_count;
      ballast.size = sub_px;
      ballast.color = QColor(0, 0, 0, 0);

      ButtonRow num_row;
      num_row.text = num;
      num_row.size = num_px;
      num_row.color = num_color;
      num_row.strikethrough = strike;
      num_row.italic = strike;

      ButtonRow count_row;
      count_row.text = day.message_count;
      count_row.size = sub_px;
      count_row.color = sub_text_color;
      count_row.strikethrough = strike;

      rows = {ballast, num_row, count_row};
    } else {
      ButtonRow num_row;
      num_row.text = num;
      num_row.size = num_px;
      num_row.color = num_color;
      num_row.strikethrough = strike;
      num_row.italic = strike;

      rows = {num_row};
    }

    // Rebuild button spec with the new rows
    ButtonRegion region;
    region.id = QStringLiteral("_main");
    region.rows = rows;
    region.toggle = true;

    buttons::ButtonSpecArgs args;
    args.shape = buttons::ShapeSpec{};
    args.shape->cornerRadius = 4;
    args.variant = QStringLiteral("ghost");

    auto spec = buttons::ButtonSpec::fromRegions({region}, args);
    btn->setSpec(spec);
    btn->syncCalendarBackground();
    btn->update();
  }
}

void CalendarWidget::updateMonthView(const CalendarViewModel& vm) {
  QColor sub_color_obj = palette_.muted_text;
  auto [title_px, sub_px] = monthYearRowSizes();

  for (const auto& mi : vm.months) {
    int idx = mi.month - 1;
    if (idx < 0 || idx >= static_cast<int>(month_buttons_.size())) continue;
    auto* btn = month_buttons_[idx];

    setButtonAvailability(btn, mi.is_available);
    setPeriodDisabledExport(btn, mi.is_disabled);

    bool strike = mi.is_disabled;
    QColor row_text = mi.is_disabled ? palette_.disabled_text : palette_.text;
    QColor row_sub =
        mi.is_disabled ? palette_.disabled_text : sub_color_obj;

    auto rows = periodRows(mi.name, mi.message_count, title_px, sub_px,
                           row_sub, strike, row_text);

    using namespace buttons;
    ButtonRegion region;
    region.id = QStringLiteral("_main");
    region.rows = rows;

    ButtonSpecArgs args;
    args.shape = buttons::ShapeSpec{};
    args.shape->cornerRadius = 6;
    args.variant = QStringLiteral("surface");

    auto spec = ButtonSpec::fromRegions({region}, args);
    btn->setSpec(spec);
    btn->update();
  }
}

void CalendarWidget::updateYearView(const CalendarViewModel& vm) {
  auto* layout = year_view_->layout();
  if (!layout) return;

  // Clear existing year buttons
  QLayoutItem* item;
  while ((item = layout->takeAt(0)) != nullptr) {
    if (auto* w = item->widget()) {
      w->deleteLater();
    }
    delete item;
  }
  year_buttons_.clear();

  QColor sub_color_obj = palette_.muted_text;
  auto [title_px, sub_px] = monthYearRowSizes();
  int min_w = std::max(50, fontUnit() * 4);
  int min_h = std::max(40, static_cast<int>(fontUnit() * 2.5));

  auto* grid = qobject_cast<QGridLayout*>(layout);
  int col = 0, row = 0;

  for (const auto& yi : vm.years) {
    auto* btn = new Button(Button::Config{
        .variant = Button::Variant::Surface,
        .cornerRadius = 6,
    }, year_view_);
    btn->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    btn->setMinimumSize(min_w, min_h);

    connect(btn, &Button::clicked, this, [this, year = yi.year]() {
      emit yearSelected(year);
    });
    connect(btn, &Button::rightClicked, this, [this, year = yi.year]() {
      emit yearContextMenu(year);
    });

    setButtonAvailability(btn, yi.is_available);
    setPeriodDisabledExport(btn, yi.is_disabled);

    bool strike = yi.is_disabled;
    QColor row_text = yi.is_disabled ? palette_.disabled_text : palette_.text;
    QColor row_sub =
        yi.is_disabled ? palette_.disabled_text : sub_color_obj;

    auto rows = periodRows(yi.name, yi.message_count, title_px, sub_px,
                           row_sub, strike, row_text);

    using namespace buttons;
    ButtonRegion region;
    region.id = QStringLiteral("_main");
    region.rows = rows;

    ButtonSpecArgs args;
    args.shape = buttons::ShapeSpec{};
    args.shape->cornerRadius = 6;
    args.variant = QStringLiteral("surface");

    auto spec = ButtonSpec::fromRegions({region}, args);
    btn->setSpec(spec);

    year_buttons_.push_back(btn);
    grid->addWidget(btn, row, col);

    col++;
    if (col > 2) {
      col = 0;
      row++;
    }
  }
  grid->setRowStretch(row + 1, 1);
}

// ============================================================================
// Public API
// ============================================================================

void CalendarWidget::setWeekdayLabels(const std::vector<QString>& names) {
  weekday_names_ = names;
  for (size_t i = 0; i < weekday_label_widgets_.size() && i < names.size();
       ++i) {
    weekday_label_widgets_[i]->setText(names[i]);
  }
}

// ============================================================================
// Event handlers
// ============================================================================

void CalendarWidget::wheelEvent(QWheelEvent* event) {
  int delta = event->angleDelta().y();
  if (delta > 0) {
    emit navigatePrevious();
  } else if (delta < 0) {
    emit navigateNext();
  }
  event->accept();
}

void CalendarWidget::resizeEvent(QResizeEvent* event) {
  QWidget::resizeEvent(event);
  if (in_resize_refresh_) return;
  if (!last_vm_.has_value()) return;

  in_resize_refresh_ = true;
  const QString& mode = last_vm_->view_mode;
  if (mode == QStringLiteral("days")) {
    updateDayView(*last_vm_);
  } else if (mode == QStringLiteral("months")) {
    updateMonthView(*last_vm_);
  } else if (mode == QStringLiteral("years")) {
    updateYearView(*last_vm_);
  }
  in_resize_refresh_ = false;
}

}  // namespace sli::toolkit