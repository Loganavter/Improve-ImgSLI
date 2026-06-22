#include "sli/toolkit/buttons/capabilities/scroll_capability.h"

#include <QWheelEvent>
#include <QWidget>

#include <algorithm>

#include "sli/toolkit/buttons/controller.h"

namespace sli::toolkit::buttons {

ScrollCapability::ScrollCapability(int minValue, int maxValue,
                                   ButtonController* controller,
                                   QObject* parent)
    : QObject(parent),
      range_(minValue, maxValue),
      controller_(controller) {
  endTimer_.setSingleShot(true);
  endTimer_.setInterval(800);
  connect(&endTimer_, &QTimer::timeout, this,
          &ScrollCapability::onScrollEnded);
}

void ScrollCapability::attach(QWidget* button,
                              std::optional<QString> regionId) {
  ButtonCapability::attach(button, regionId);
  setParent(button);
  endTimer_.stop();
}

void ScrollCapability::detach(QWidget* button) {
  endTimer_.stop();
  ButtonCapability::detach(button);
}

bool ScrollCapability::isEnabled() const {
  return button_ != nullptr && button_->isEnabled();
}

bool ScrollCapability::handleWheelEvent(QWheelEvent* event) {
  if (!isEnabled() || controller_ == nullptr) {
    return false;
  }
  const int delta = event->angleDelta().y();
  if (delta == 0) {
    return false;
  }
  const int step = delta > 0 ? 1 : -1;
  const int current = controller_->scrollValue(regionId_).value_or(range_.first);
  const int next = std::clamp(current + step, range_.first, range_.second);
  if (next != current) {
    controller_->setScrollValue(regionId_, next);
    emit scrollValueChanged(regionId_, next);
  }
  if (!endTimer_.isActive()) {
    emit scrollStarted(regionId_);
  }
  endTimer_.start();
  event->accept();
  if (button_ != nullptr) {
    button_->update();
  }
  return true;
}

void ScrollCapability::onScrollEnded() {
  emit scrollEnded(regionId_);
  if (button_ != nullptr) {
    button_->update();
  }
}

}  // namespace sli::toolkit::buttons
