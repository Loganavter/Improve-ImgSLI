#include "sli/toolkit/composite/unified_flyout/simple_adapter.h"

#include "sli/toolkit/composite/unified_flyout/panel.h"

namespace sli::toolkit::unified_flyout {

void SimpleAdapter::populate(
    Panel* panel,
    const std::vector<std::pair<QString, QVariant>>& items) {
  if (panel == nullptr) {
    return;
  }
  std::vector<FlyoutItem> flyoutItems;
  flyoutItems.reserve(items.size());
  for (const auto& [label, data] : items) {
    FlyoutItem item;
    item.name = label;
    item.data = data;
    flyoutItems.push_back(std::move(item));
  }
  panel->setItems(std::move(flyoutItems));
}

}  // namespace sli::toolkit::unified_flyout
