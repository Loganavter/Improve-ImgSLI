#include "sli/toolkit/atomic/divider.h"

#include <QPainter>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

Divider::Divider(Qt::Orientation orientation, QWidget* parent)
    : QWidget(parent), orientation_(orientation) {
  setObjectName(QStringLiteral("sliDivider"));
  setOrientation(orientation);
}

void Divider::setOrientation(Qt::Orientation orientation) {
  orientation_ = orientation;
  if (orientation_ == Qt::Horizontal) {
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
    setFixedHeight(9);
    setMaximumWidth(QWIDGETSIZE_MAX);
  } else {
    setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
    setFixedWidth(9);
    setMaximumHeight(QWIDGETSIZE_MAX);
  }
  updateGeometry();
  update();
}

QSize Divider::sizeHint() const {
  return orientation_ == Qt::Horizontal ? QSize(80, 9) : QSize(9, 24);
}

void Divider::paintEvent(QPaintEvent*) {
  QPainter painter(this);
  painter.setPen(QPen(Theme::palette().border, 1.0));
  if (orientation_ == Qt::Horizontal) {
    const int y = height() / 2;
    painter.drawLine(0, y, width(), y);
  } else {
    const int x = width() / 2;
    painter.drawLine(x, 0, x, height());
  }
}

}  // namespace sli::toolkit
