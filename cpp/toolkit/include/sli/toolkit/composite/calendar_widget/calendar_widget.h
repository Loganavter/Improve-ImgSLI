#pragma once

#include <QColor>
#include <QLabel>
#include <QPointer>
#include <QString>
#include <QWidget>

#include <optional>
#include <vector>

class QGridLayout;
class QStackedWidget;

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/content/button_row.h"
#include "sli/toolkit/composite/calendar_widget/calendar_day_button.h"
#include "sli/toolkit/composite/calendar_widget/calendar_models.h"

namespace sli::toolkit {

/// Generic three-level calendar (days / months / years).
/// Feed data via updateView(CalendarViewModel).
/// Connect to signals for navigation and selection.
class CalendarWidget : public QWidget {
  Q_OBJECT

 public:
  explicit CalendarWidget(
      QWidget* parent = nullptr,
      const std::vector<QString>& weekday_labels = {},
      const std::optional<QColor>& accent_color = std::nullopt,
      const std::optional<QColor>& hover_color = std::nullopt,
      const std::optional<QColor>& text_color = std::nullopt,
      const std::optional<QColor>& bg_color = std::nullopt,
      const std::optional<QColor>& data_bg = std::nullopt,
      const std::optional<QColor>& weekend_bg = std::nullopt,
      const std::optional<QColor>& disabled_bg = std::nullopt);
  ~CalendarWidget() override = default;

  void updateView(const CalendarViewModel& vm);
  void setWeekdayLabels(const std::vector<QString>& names);

  /// Override one or more colors; passing std::nullopt clears the override.
  void setColors(
      std::optional<QColor> accent_color = std::nullopt,
      std::optional<QColor> hover_color = std::nullopt,
      std::optional<QColor> text_color = std::nullopt,
      std::optional<QColor> bg_color = std::nullopt,
      std::optional<QColor> data_bg = std::nullopt,
      std::optional<QColor> weekend_bg = std::nullopt,
      std::optional<QColor> disabled_bg = std::nullopt);

 signals:
  void dateClicked(QDate date);
  void dateContextMenu(QDate date);
  void monthSelected(int year, int month);
  void monthContextMenu(int year, int month);
  void yearSelected(int year);
  void yearContextMenu(int year);

  void navigatePrevious();
  void navigateNext();
  void titleClicked();

 protected:
  void wheelEvent(QWheelEvent* event) override;
  void resizeEvent(QResizeEvent* event) override;

 private:
  // Color palette helpers
  struct CalendarPalette {
    QColor accent;
    QColor hover;
    QColor text;
    QColor bg;
    QColor data_bg;
    QColor weekend_bg;
    QColor disabled_bg;
    QColor muted_text;
    QColor data_text;
    QColor disabled_text;
  };

  static QColor mixColors(const QColor& first, const QColor& second,
                          double first_weight);
  static QColor contrastColor(const QColor& color);
  QColor fadedColor(double factor = 0.6) const;
  void resolvePalette();
  void applyStyles();

  // Dimension helpers (mirror Python)
  int fontUnit() const;
  int spacingUnit() const;
  int navButtonSize() const;
  std::pair<int, int> monthYearRowSizes() const;

  // Input helpers
  void setButtonAvailability(Button* btn, bool is_available);
  void setPeriodDisabledExport(Button* btn, bool is_disabled);

  // Row builders
  std::vector<buttons::ButtonRow> periodRows(
      const QString& title, const QString& value, int title_px, int sub_px,
      const QColor& sub_color, bool strike,
      const std::optional<QColor>& title_color = std::nullopt) const;

  // UI setup
  void setupUi();
  QWidget* createDayView();
  QWidget* createMonthView();
  QWidget* createYearView();

  // View updates
  void updateDayView(const CalendarViewModel& vm);
  void updateMonthView(const CalendarViewModel& vm);
  void updateYearView(const CalendarViewModel& vm);

  // Theme change callback
  void onThemeChanged();

  // Default weekday labels (English)
  static std::vector<QString> defaultWeekdayLabels();

  int current_year_ = QDate::currentDate().year();

  CalendarPalette palette_;
  // Color overrides keyed by name: accent, hover, text, bg, data_bg,
  // weekend_bg, disabled_bg
  struct ColorOverrides {
    std::optional<QColor> accent;
    std::optional<QColor> hover;
    std::optional<QColor> text;
    std::optional<QColor> bg;
    std::optional<QColor> data_bg;
    std::optional<QColor> weekend_bg;
    std::optional<QColor> disabled_bg;
  };
  ColorOverrides color_overrides_;

  // Widgets
  Button* prev_button_ = nullptr;
  Button* title_button_ = nullptr;
  Button* next_button_ = nullptr;
  QStackedWidget* view_stack_ = nullptr;
  QWidget* day_view_ = nullptr;
  QWidget* month_view_ = nullptr;
  QWidget* year_view_ = nullptr;

  std::vector<CalendarDayButton*> day_buttons_;
  std::vector<Button*> month_buttons_;
  std::vector<Button*> year_buttons_;
  std::vector<QLabel*> weekday_label_widgets_;
  std::vector<QString> weekday_names_;

  std::optional<CalendarViewModel> last_vm_;
  bool in_resize_refresh_ = false;
};

}  // namespace sli::toolkit