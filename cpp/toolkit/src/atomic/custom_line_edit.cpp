#include "sli/toolkit/atomic/custom_line_edit.h"

#include <QColor>
#include <QFocusEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPen>
#include <QRectF>
#include <Qt>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

CustomLineEdit::CustomLineEdit(QWidget* parent) : QLineEdit(parent) {
  setFrame(false);
  setTextMargins(kHPadding, kVPadding, kHPadding, kVPadding);
}

void CustomLineEdit::setUnderlineColor(const QColor& color) {
  underlineColor_ = color;
  update();
}

void CustomLineEdit::setFocusedUnderlineColor(const QColor& color) {
  focusedUnderlineColor_ = color;
  update();
}

void CustomLineEdit::setUnderlineThickness(double thickness) {
  underlineThickness_ = thickness;
  update();
}

void CustomLineEdit::paintEvent(QPaintEvent* event) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);
  const Palette& palette = Theme::palette();

  const QRectF r = QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5);
  p.setPen(QPen(palette.border, 1));
  p.setBrush(palette.base);
  p.drawRoundedRect(r, kRadius, kRadius);

  // Optional underline accent.
  const QColor underline = hasFocus()
                                ? focusedUnderlineColor_.value_or(palette.accent)
                                : underlineColor_.value_or(QColor(0, 0, 0, 0));
  if (underline.alpha() > 0) {
    p.setPen(QPen(underline, underlineThickness_));
    const int y = r.bottom();
    p.drawLine(static_cast<int>(r.left() + kRadius), y,
               static_cast<int>(r.right() - kRadius), y);
  }
  p.end();
  QLineEdit::paintEvent(event);
}

void CustomLineEdit::focusInEvent(QFocusEvent* event) {
  QLineEdit::focusInEvent(event);
  update();
}

void CustomLineEdit::focusOutEvent(QFocusEvent* event) {
  QLineEdit::focusOutEvent(event);
  update();
}

}  // namespace sli::toolkit
