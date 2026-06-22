#include "sli/toolkit/atomic/loading_spinner.h"

#include <QBrush>
#include <QColor>
#include <QConicalGradient>
#include <QPainter>
#include <QPainterPath>
#include <QPaintEvent>
#include <QPointF>
#include <Qt>

#include <algorithm>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

LoadingSpinner::LoadingSpinner(QWidget* parent) : QWidget(parent) {
  setFixedSize(40, 40);
  connect(&timer_, &QTimer::timeout, this, &LoadingSpinner::tick);
}

void LoadingSpinner::start() {
  if (!timer_.isActive()) {
    timer_.start(15);
  }
}

void LoadingSpinner::stop() { timer_.stop(); }

void LoadingSpinner::tick() {
  angle_ = (angle_ + 6) % 360;
  update();
}

void LoadingSpinner::paintEvent(QPaintEvent*) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);
  const QPointF center(rect().center());
  const double radius = std::min(width(), height()) / 2.0;

  QConicalGradient gradient(center, static_cast<qreal>(-angle_));
  QColor accent = Theme::palette().accent;
  QColor transparent = accent;
  transparent.setAlpha(0);
  gradient.setColorAt(0.0, accent);
  gradient.setColorAt(0.1, accent);
  gradient.setColorAt(1.0, transparent);

  const double thickness = std::max(2.0, radius * 0.18);
  QPainterPath ring;
  ring.addEllipse(center, radius - thickness * 0.5,
                  radius - thickness * 0.5);
  ring.addEllipse(center, radius - thickness * 1.5,
                  radius - thickness * 1.5);
  p.setBrush(gradient);
  p.setPen(Qt::NoPen);
  p.drawPath(ring);
}

}  // namespace sli::toolkit
