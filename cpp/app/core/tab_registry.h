// Static-registration registry for workspace tabs. C++ port of
// src/tabs/registry.py — uses an explicit registration macro since pkgutil
// auto-discovery does not translate.

#pragma once

#include <QString>
#include <vector>

#include "imgsli/contracts/tab_contract.h"

namespace imgsli::app {

class TabRegistry final {
 public:
  static TabRegistry& instance();

  /// Insertion-ordered, owned by the registry.
  const std::vector<imgsli::contracts::TabContract*>& tabs() const {
    return tabs_;
  }

  imgsli::contracts::TabContract* find(const QString& sessionType) const;

  /// Register a tab. Ownership transfers to the registry.
  void registerTab(imgsli::contracts::TabContract* tab);

 private:
  TabRegistry() = default;
  TabRegistry(const TabRegistry&) = delete;
  TabRegistry& operator=(const TabRegistry&) = delete;

  std::vector<imgsli::contracts::TabContract*> tabs_;
};

/// Helper for static registration at translation-unit init time.
class TabAutoRegister final {
 public:
  explicit TabAutoRegister(imgsli::contracts::TabContract* tab) {
    TabRegistry::instance().registerTab(tab);
  }
};

#define IMGSLI_REGISTER_TAB(Type)                                            \
  static ::imgsli::app::TabAutoRegister _imgsli_tab_register_##Type(new Type)

}  // namespace imgsli::app
