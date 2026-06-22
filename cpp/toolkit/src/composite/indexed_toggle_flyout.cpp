#include "sli/toolkit/composite/indexed_toggle_flyout.h"

#include <QHBoxLayout>

namespace sli::toolkit {

IndexedToggleFlyout::IndexedToggleFlyout(QWidget* parentWidget,
                                         int slotCount,
                                         QIcon slotIcon,
                                         int buttonSize)
    : Flyout(parentWidget),
      slotIcon_(slotIcon),
      buttonSize_(buttonSize),
      hLayout_(new QHBoxLayout()) {
  setObjectName(QStringLiteral("sliIndexedToggleFlyout"));
  hLayout_->setContentsMargins(0, 0, 0, 0);
  hLayout_->setSpacing(6);
  contentLayout_->addLayout(hLayout_);

  autoHideTimer_ = new QTimer(this);
  autoHideTimer_->setSingleShot(true);
  connect(autoHideTimer_, &QTimer::timeout, this, &QWidget::hide);

  setSlotCount(slotCount);
  hide();
}

const std::vector<Button*>& IndexedToggleFlyout::buttons() const {
  return buttons_;
}

void IndexedToggleFlyout::setSlotCount(int slotCount) {
  slotCount = std::max(0, slotCount);

  // Create new buttons if needed — mirrors Python while loop
  while (static_cast<int>(buttons_.size()) < slotCount) {
    int index = static_cast<int>(buttons_.size()) + 1;
    Button::Config config;
    config.icon = slotIcon_;
    config.toggle = true;
    config.badge = QVariant::fromValue(index);
    config.size = QSize(buttonSize_, buttonSize_);

    auto* button = new Button(config, this);
    // Mirror Python: button.set_show_strike_through(True)
    {
      auto s = button->spec();
      if (!s.regions.empty()) {
        s.regions[0].badge = QVariant::fromValue(index);
        s.regions[0].style.showStrikeThrough = true;
      }
      button->setSpec(std::move(s));
    }
    hLayout_->addWidget(button);
    buttons_.push_back(button);
  }

  // Show/hide and update badges — mirrors Python enumerate
  for (size_t i = 0; i < buttons_.size(); ++i) {
    bool visible = static_cast<int>(i) < slotCount;
    buttons_[i]->setVisible(visible);
    auto s = buttons_[i]->spec();
    if (!s.regions.empty()) {
      if (visible) {
        s.regions[0].badge = QVariant::fromValue(static_cast<int>(i) + 1);
      } else {
        s.regions[0].badge = QVariant{};
      }
    }
    buttons_[i]->setSpec(std::move(s));
  }

  refreshLayout();
}

void IndexedToggleFlyout::setSlots(
    const std::vector<bool>& activeStates,
    const std::vector<std::optional<int>>& displayNumbers) {
  setSlotCount(static_cast<int>(activeStates.size()));
  for (size_t i = 0; i < activeStates.size() && i < buttons_.size(); ++i) {
    // Python: button.setChecked(not bool(is_active), emit_signal=False)
    buttons_[i]->setChecked(!activeStates[i]);

    std::optional<int> displayNumber;
    if (i < displayNumbers.size()) {
      displayNumber = displayNumbers[i];
    }
    auto s = buttons_[i]->spec();
    if (!s.regions.empty()) {
      if (displayNumber.has_value()) {
        s.regions[0].badge = QVariant::fromValue(*displayNumber);
      } else {
        s.regions[0].badge = QVariant{};
      }
    }
    buttons_[i]->setSpec(std::move(s));
  }
  refreshLayout();
}

void IndexedToggleFlyout::refreshLayout() {
  hLayout_->invalidate();
  hLayout_->activate();
  updateGeometry();
  adjustSize();
}

void IndexedToggleFlyout::showForButton(QWidget* anchorBtn,
                                        QWidget* /*parentWidget*/,
                                        int hoverDelayMs) {
  auto doShow = [this, anchorBtn]() {
    anchorButton_ = anchorBtn;
    showAligned(anchorBtn, QStringLiteral("top-center"),
                QStringLiteral("bottom-center"));
  };

  if (hoverDelayMs > 0) {
    QTimer::singleShot(hoverDelayMs, this, doShow);
  } else {
    doShow();
  }
}

void IndexedToggleFlyout::scheduleAutoHide(int ms) {
  if (autoHideTimer_) {
    autoHideTimer_->start(ms);
  }
}

void IndexedToggleFlyout::cancelAutoHide() {
  if (autoHideTimer_) {
    autoHideTimer_->stop();
  }
}

void IndexedToggleFlyout::hide() {
  cancelAutoHide();
  Flyout::hide();
}

}  // namespace sli::toolkit