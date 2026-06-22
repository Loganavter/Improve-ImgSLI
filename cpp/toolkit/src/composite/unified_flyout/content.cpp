#include "sli/toolkit/composite/unified_flyout/content.h"

#include "sli/toolkit/composite/unified_flyout/panel.h"

namespace sli::toolkit::unified_flyout {

void ContentAdapter::populate(Panel* panel, std::vector<FlyoutItem> items,
                               int currentIndex) {
  if (panel == nullptr) {
    return;
  }
  panel->setItems(std::move(items));
  panel->setCurrentIndex(currentIndex);
}

}  // namespace sli::toolkit::unified_flyout
