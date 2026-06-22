#include "sli/toolkit/buttons/layers/ripple.h"

#include <QWidget>

#include <algorithm>

namespace sli::toolkit::buttons {

RippleEffect::RippleEffect(QWidget* widget) : QObject(widget), widget_(widget) {
  timer_.setInterval(kTickMs);
  connect(&timer_, &QTimer::timeout, this, &RippleEffect::onTick);
}

void RippleEffect::trigger(const QPointF& origin,
                           std::optional<QColor> colorFrom,
                           std::optional<QColor> colorTo) {
  center_ = origin;
  elapsedMs_ = 0;
  colorFrom_ = colorFrom;
  colorTo_ = colorTo;
  timer_.start();
  if (widget_ != nullptr) {
    widget_->update();
  }
}

double RippleEffect::progress() const {
  return std::min(1.0,
                  static_cast<double>(elapsedMs_) / static_cast<double>(kDurationMs));
}

void RippleEffect::onTick() {
  elapsedMs_ += kTickMs;
  if (elapsedMs_ >= kDurationMs) {
    timer_.stop();
    center_.reset();
    colorFrom_.reset();
    colorTo_.reset();
  }
  if (widget_ == nullptr || !widget_->isVisible()) {
    timer_.stop();
    center_.reset();
    colorFrom_.reset();
    colorTo_.reset();
    return;
  }
  widget_->update();
}

}  // namespace sli::toolkit::buttons
