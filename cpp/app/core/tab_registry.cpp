#include "core/tab_registry.h"

namespace imgsli::app {

TabRegistry& TabRegistry::instance() {
  static TabRegistry registry;
  return registry;
}

void TabRegistry::registerTab(imgsli::contracts::TabContract* tab) {
  if (tab == nullptr) {
    return;
  }
  tabs_.push_back(tab);
}

imgsli::contracts::TabContract* TabRegistry::find(
    const QString& sessionType) const {
  for (auto* tab : tabs_) {
    if (tab != nullptr && tab->sessionType() == sessionType) {
      return tab;
    }
  }
  return nullptr;
}

}  // namespace imgsli::app
