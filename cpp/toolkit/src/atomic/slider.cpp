#include "sli/toolkit/atomic/slider.h"

#include <QColor>
#include <QEasingCurve>
#include <QEnterEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPen>
#include <QRectF>

#include <algorithm>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

Slider::Slider(Qt::Orientation orientation, QWidget* parent)
    : QSlider(orientation, parent), animInner_(this, "innerScale") {
  setMouseTracking(true);
  setAttribute(Qt::WA_Hover, true);
  setFocusPolicy(Qt::StrongFocus);
  setCursor(Qt::PointingHandCursor);
  animInner_.setDuration(140);
  animInner_.setEasingCurve(QEasingCurve::OutCubic);
  if (maximum() == 99 && minimum() == 0) {
    setMaximum(100);
  }
}

void Slider::setInnerScale(double value) {
  value = std::clamp(value, 0.0, 1.0);
  if (std::abs(value - innerScale_) > 1e-4) {
    innerScale_ = value;
    update();
  }
}

void Slider::animateInnerScale(double target) {
  animInner_.stop();
  animInner_.setStartValue(innerScale_);
  animInner_.setEndValue(target);
  animInner_.start();
}

void Slider::paintEvent(QPaintEvent*) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);
  const Palette& palette = Theme::palette();
  const QRect r = rect();

  if (orientation() == Qt::Horizontal) {
    const int y = r.height() / 2 - kTrackHeight / 2;
    const QRect trackBg(kMarginH, y, r.width() - 2 * kMarginH, kTrackHeight);
    p.setPen(Qt::NoPen);
    p.setBrush(palette.border);
    p.drawRoundedRect(trackBg, kTrackHeight / 2.0, kTrackHeight / 2.0);

    const double t = static_cast<double>(value() - minimum()) /
                     std::max(1, maximum() - minimum());
    const int filledW = static_cast<int>(trackBg.width() * t);
    if (filledW > 0) {
      QRect filled = trackBg;
      filled.setWidth(filledW);
      p.setBrush(palette.accent);
      p.drawRoundedRect(filled, kTrackHeight / 2.0, kTrackHeight / 2.0);
    }

    const int hx = trackBg.left() + filledW;
    const int hy = trackBg.center().y();
    const double outerR = kHandleRadius * (hovered_ || pressed_ ? 1.0 : 0.85);
    const double innerR = outerR * innerScale_;
    p.setBrush(palette.base);
    p.setPen(QPen(palette.border, 1.0));
    p.drawEllipse(QRectF(hx - outerR, hy - outerR, outerR * 2, outerR * 2));
    p.setBrush(palette.accent);
    p.setPen(Qt::NoPen);
    p.drawEllipse(QRectF(hx - innerR, hy - innerR, innerR * 2, innerR * 2));
  } else {
    const int x = r.width() / 2 - kTrackHeight / 2;
    const QRect trackBg(x, kMarginH, kTrackHeight, r.height() - 2 * kMarginH);
    p.setPen(Qt::NoPen);
    p.setBrush(palette.border);
    p.drawRoundedRect(trackBg, kTrackHeight / 2.0, kTrackHeight / 2.0);
    const double t = static_cast<double>(value() - minimum()) /
                     std::max(1, maximum() - minimum());
    const int filledH = static_cast<int>(trackBg.height() * t);
    if (filledH > 0) {
      QRect filled = trackBg;
      filled.setTop(trackBg.bottom() - filledH);
      p.setBrush(palette.accent);
      p.drawRoundedRect(filled, kTrackHeight / 2.0, kTrackHeight / 2.0);
    }
    const int hy = trackBg.bottom() - filledH;
    const int hx = trackBg.center().x();
    const double outerR = kHandleRadius * (hovered_ || pressed_ ? 1.0 : 0.85);
    const double innerR = outerR * innerScale_;
    p.setBrush(palette.base);
    p.setPen(QPen(palette.border, 1.0));
    p.drawEllipse(QRectF(hx - outerR, hy - outerR, outerR * 2, outerR * 2));
    p.setBrush(palette.accent);
    p.setPen(Qt::NoPen);
    p.drawEllipse(QRectF(hx - innerR, hy - innerR, innerR * 2, innerR * 2));
  }
}

void Slider::enterEvent(QEnterEvent* event) {
  hovered_ = true;
  animateInnerScale(0.85);
  QSlider::enterEvent(event);
}

void Slider::leaveEvent(QEvent* event) {
  hovered_ = false;
  animateInnerScale(0.50);
  QSlider::leaveEvent(event);
}

void Slider::mousePressEvent(QMouseEvent* event) {
  pressed_ = true;
  animateInnerScale(1.0);
  QSlider::mousePressEvent(event);
}

void Slider::mouseReleaseEvent(QMouseEvent* event) {
  pressed_ = false;
  animateInnerScale(hovered_ ? 0.85 : 0.50);
  QSlider::mouseReleaseEvent(event);
}

}  // namespace sli::toolkit
