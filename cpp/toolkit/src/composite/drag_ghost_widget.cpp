#include "sli/toolkit/composite/drag_ghost_widget.h"

#include <QGraphicsOpacityEffect>
#include <QPainter>
#include <QPainterPath>
#include <QPixmap>

namespace sli::toolkit {

DragGhostWidget::DragGhostWidget(QWidget* parent) : QWidget(parent) {
  if (parent == nullptr) {
    throw std::invalid_argument(
        "DragGhostWidget requires an in-window parent widget");
  }
  setWindowFlags(Qt::Widget);
  setAttribute(Qt::WA_TranslucentBackground);
  setAttribute(Qt::WA_ShowWithoutActivating);
  setAttribute(Qt::WA_TransparentForMouseEvents);
  opacityEffect_ = new QGraphicsOpacityEffect(this);
  setGraphicsEffect(opacityEffect_);
  setOpacity(1.0);
}

void DragGhostWidget::setPixmap(const QPixmap& pixmap) {
  pixmap_ = pixmap;
  setFixedSize(pixmap.size());
  update();
}

void DragGhostWidget::setOpacity(qreal opacity) {
  opacityEffect_->setOpacity(std::max(0.0, std::min(1.0, opacity)));
}

void DragGhostWidget::move(const QPoint& pos) {
  if (parentWidget() != nullptr) {
    QWidget::move(parentWidget()->mapFromGlobal(pos));
  } else {
    QWidget::move(pos);
  }
}

void DragGhostWidget::paintEvent(QPaintEvent*) {
  if (pixmap_.isNull()) return;

  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing, true);
  painter.setRenderHint(QPainter::SmoothPixmapTransform, true);

  QRectF rect(QPointF(0, 0), size());
  QPainterPath path;
  path.addRoundedRect(rect, 8.0, 8.0);
  painter.setClipPath(path);
  painter.drawPixmap(rect.toRect(), pixmap_);
}

}  // namespace sli::toolkit