#include "sli/toolkit/buttons/capabilities/long_press_capability.h"

#include <QWidget>

namespace sli::toolkit::buttons {

LongPressCapability::LongPressCapability(int delayMs, QObject* parent)
    : QObject(parent), delayMs_(delayMs) {
  timer_.setSingleShot(true);
  timer_.setInterval(delayMs_);
  connect(&timer_, &QTimer::timeout, this, &LongPressCapability::onTimeout);
}

void LongPressCapability::attach(QWidget* button,
                                 std::optional<QString> regionId) {
  ButtonCapability::attach(button, regionId);
  // Mirror Python — the capability lives in the button's QObject tree so
  // findChild<>() / observe-by-walk works, and ownership tracks the button.
  setParent(button);
  triggered_ = false;
}

void LongPressCapability::detach(QWidget* button) {
  timer_.stop();
  ButtonCapability::detach(button);
}

bool LongPressCapability::isEnabled() const {
  return button_ != nullptr && button_->isEnabled();
}

void LongPressCapability::onPressStart() {
  if (!isEnabled()) {
    return;
  }
  triggered_ = false;
  timer_.start();
}

void LongPressCapability::onPressEnd() {
  timer_.stop();
  triggered_ = false;
}

void LongPressCapability::onTimeout() {
  if (button_ == nullptr) {
    return;
  }
  triggered_ = true;
  emit longPressed(regionId_);
}

}  // namespace sli::toolkit::buttons
