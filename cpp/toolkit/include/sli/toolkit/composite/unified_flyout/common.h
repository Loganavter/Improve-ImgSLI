#pragma once

#include <QGraphicsEffect>
#include <QPainter>
#include <QPainterPath>
#include <QRectF>
#include <Qt>

namespace sli::toolkit::unified_flyout {

enum class FlyoutMode {
  Hidden,
  SingleLeft,
  SingleRight,
  Double,
  SingleSimple,
};

class RoundedClipEffect : public QGraphicsEffect {
  Q_OBJECT

 public:
  explicit RoundedClipEffect(int radius = 8, QObject* parent = nullptr)
      : QGraphicsEffect(parent), radius_(radius) {}

  void setRadius(int radius) {
    radius_ = radius;
    update();
  }

 protected:
  void draw(QPainter* painter) override {
    const QRectF src = sourceBoundingRect();
    if (src.isEmpty()) {
      return;
    }
    QPainterPath clip;
    clip.addRoundedRect(src, radius_, radius_);
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing);
    painter->setClipPath(clip, Qt::IntersectClip);
    drawSource(painter);
    painter->restore();
  }

 private:
  int radius_;
};

// Port of Python `draw_rounded_shadow` — concentric rounded rects with
// quadratic-alpha falloff.  `steps` iterations from black at alpha_max down
// to transparent, each step growing outward by 1 px.
//
// Python signature:
//   draw_rounded_shadow(painter, rect, steps=10, radius=8, alpha_max=34)
inline void drawRoundedShadow(QPainter* painter,
                               const QRectF& rect,
                               int steps,
                               double radius,
                               int alphaMax = 34) {
  painter->setPen(Qt::NoPen);
  for (int i = 0; i < steps; ++i) {
    const double t = 1.0 - static_cast<double>(i) / steps;
    const int alpha = static_cast<int>(alphaMax * t * t);
    painter->setBrush(QColor(0, 0, 0, alpha));
    const QRectF shadowRect = rect.adjusted(-i, -i + 1, i, i + 1);
    painter->drawRoundedRect(shadowRect, radius + i, radius + i);
  }
}

}  // namespace sli::toolkit::unified_flyout
