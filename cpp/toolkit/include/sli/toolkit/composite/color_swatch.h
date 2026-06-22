#pragma once

#include <QColor>
#include <QPointer>

#include "sli/toolkit/buttons/button.h"

class QColorDialog;

namespace sli::toolkit {

/// Round Button that opens a themed QColorDialog on click.
/// Mirrors Python's ColorSwatch.
class ColorSwatch : public Button {
  Q_OBJECT

 public:
  explicit ColorSwatch(QColor color = QColor(255, 255, 255), int size = 28,
                       bool alpha = true, QWidget* parent = nullptr);

  QColor color() const;
  void setColor(QColor color);
  void set_color(QColor color) { setColor(color); }

 signals:
  void colorChanged(QColor color);

 private:
  void refreshBorder();
  void openDialog();

  QColor color_;
  QPointer<QColorDialog> dialog_;
  bool alpha_ = true;
};

}  // namespace sli::toolkit