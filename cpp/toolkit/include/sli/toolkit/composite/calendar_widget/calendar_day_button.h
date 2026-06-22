#pragma once

#include <QDate>
#include <QPointer>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/buttons/content/button_row.h"

namespace sli::toolkit {

/// A single day cell in CalendarWidget. Mirrors Python's CalendarDayButton.
class CalendarDayButton : public Button {
  Q_OBJECT

 public:
  explicit CalendarDayButton(QWidget* parent = nullptr);
  ~CalendarDayButton() override = default;

  /// Set rows content (mirrors Python's btn.setRows(rows, compact=True)).
  /// Rebuilds the button spec with current calendar state merged in.
  void setRows(const std::vector<buttons::ButtonRow>& rows,
               bool compact = true);

  void setData(bool has_data, const QColor& color = QColor());
  void setDate(const QDate& date);
  void setWeekend(bool is_weekend, const QColor& color = QColor());
  void setDisabledExport(bool is_disabled, const QColor& color = QColor());

  /// Override to accept an optional emit flag (ignored in C++ — always emits
  /// when signals are not blocked).
  void setChecked(bool checked, bool /*emit_unused*/ = true) {
    Button::setChecked(checked);
    rebuildSpec();
  }

  QDate buttonDate() const { return date_; }

  QSize sizeHint() const override { return QSize(50, 70); }
  QSize minimumSizeHint() const override { return QSize(28, 36); }

 signals:
  void dateClicked(QDate date);
  void dateContextMenu(QDate date);

 private:
  void rebuildSpec();
  void onButtonClicked();
  void onContextMenu(const QPoint& pos);

  QDate date_;
  bool is_weekend_ = false;
  QColor weekend_color_;
  bool is_disabled_export_ = false;
  QColor disabled_export_color_;
  bool has_data_ = false;
  QColor data_color_;

  std::vector<buttons::ButtonRow> current_rows_;
  bool current_compact_ = true;
};

}  // namespace sli::toolkit