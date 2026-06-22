#include "sli/toolkit/atomic/icon.h"

#include <QPainter>

namespace sli::toolkit {

Icon::Icon(const QIcon& icon, QWidget* parent)
    : QWidget(parent), icon_(icon) {
  setObjectName(QStringLiteral("sliIcon"));
  setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
}

void Icon::setIcon(const QIcon& icon) {
  icon_ = icon;
  update();
}

void Icon::setIconSize(const QSize& size) {
  if (!size.isValid() || size.isEmpty()) {
    return;
  }
  iconSize_ = size;
  updateGeometry();
  update();
}

void Icon::setTintColor(const QColor& color) {
  tintColor_ = color;
  update();
}

void Icon::clearTintColor() {
  tintColor_ = {};
  update();
}

QSize Icon::sizeHint() const {
  return iconSize_ + QSize(4, 4);
}

void Icon::paintEvent(QPaintEvent*) {
  if (icon_.isNull()) {
    return;
  }
  QPixmap pixmap = icon_.pixmap(
      iconSize_, isEnabled() ? QIcon::Normal : QIcon::Disabled);
  if (tintColor_.isValid()) {
    QPainter tint(&pixmap);
    tint.setCompositionMode(QPainter::CompositionMode_SourceIn);
    QColor color = tintColor_;
    if (!isEnabled()) {
      color.setAlpha(110);
    }
    tint.fillRect(pixmap.rect(), color);
  }
  QPainter painter(this);
  const QPoint topLeft((width() - pixmap.width() / pixmap.devicePixelRatio()) / 2,
                       (height() - pixmap.height() / pixmap.devicePixelRatio()) /
                           2);
  painter.drawPixmap(topLeft, pixmap);
}

}  // namespace sli::toolkit
