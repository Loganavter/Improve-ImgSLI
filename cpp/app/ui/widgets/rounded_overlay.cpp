#include "ui/widgets/rounded_overlay.h"

#include <QPainter>

namespace imgsli::app::ui::widgets {

RoundedOverlayWidget::RoundedOverlayWidget(QWidget* parent, QColor bgColor,
                                           qreal radius)
    : QWidget(parent), bgColor_(std::move(bgColor)), radius_(radius) {
  setAttribute(Qt::WA_NoSystemBackground, true);
  setAttribute(Qt::WA_TranslucentBackground, true);
}

void RoundedOverlayWidget::setBackgroundColor(const QColor& color) {
  bgColor_ = color;
  update();
}

void RoundedOverlayWidget::setRadius(qreal radius) {
  radius_ = radius;
  update();
}

void RoundedOverlayWidget::paintEvent(QPaintEvent* /*event*/) {
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing, true);
  painter.setCompositionMode(QPainter::CompositionMode_Source);
  painter.fillRect(rect(), QColor(0, 0, 0, 0));
  painter.setCompositionMode(QPainter::CompositionMode_SourceOver);
  painter.setPen(Qt::NoPen);
  painter.setBrush(bgColor_);
  painter.drawRoundedRect(rect(), radius_, radius_);
}

}  // namespace imgsli::app::ui::widgets
