#include "sli/toolkit/composite/unified_flyout/refresh.h"

#include "sli/toolkit/composite/unified_flyout/panel.h"

namespace sli::toolkit::unified_flyout {

RefreshPolicy::RefreshPolicy(Panel* panel, Producer producer, QObject* parent)
    : QObject(parent), panel_(panel), producer_(std::move(producer)) {
  debounceTimer_.setSingleShot(true);
  debounceTimer_.setInterval(120);
  connect(&debounceTimer_, &QTimer::timeout, this, &RefreshPolicy::doReload);
}

void RefreshPolicy::setDebounceMs(int ms) { debounceTimer_.setInterval(ms); }

void RefreshPolicy::requestReload() { debounceTimer_.start(); }

void RefreshPolicy::doReload() {
  if (panel_ != nullptr && producer_) {
    panel_->setItems(producer_());
  }
}

}  // namespace sli::toolkit::unified_flyout
