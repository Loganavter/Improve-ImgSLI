#pragma once

#include <QHBoxLayout>
#include <QIcon>
#include <QPointer>
#include <QTimer>
#include <QWidget>

#include <vector>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/composite/flyout.h"

namespace sli::toolkit {

/// Flyout with a horizontal row of numbered toggle buttons.
/// Mirrors Python's IndexedToggleFlyout.
class IndexedToggleFlyout : public Flyout {
  Q_OBJECT

 public:
  explicit IndexedToggleFlyout(QWidget* parentWidget,
                               int slotCount = 3,
                               QIcon slotIcon = {},
                               int buttonSize = 28);

  const std::vector<Button*>& buttons() const;

  void setSlotCount(int slotCount);
  void setSlots(const std::vector<bool>& activeStates,
                const std::vector<std::optional<int>>& displayNumbers = {});

  void showForButton(QWidget* anchorBtn,
                     QWidget* /*parentWidget*/ = nullptr,
                     int hoverDelayMs = 0);

  void scheduleAutoHide(int ms);
  void cancelAutoHide();

 public slots:
  void hide();

 private:
  void refreshLayout();

  QHBoxLayout* hLayout_ = nullptr;
  std::vector<Button*> buttons_;
  QPointer<QWidget> anchorButton_;
  QIcon slotIcon_;
  int buttonSize_ = 28;
  QTimer* autoHideTimer_ = nullptr;
};

}  // namespace sli::toolkit