// Static-registration plugin registry. Same shape as TabRegistry —
// explicit IMGSLI_REGISTER_PLUGIN macros for each plugin .cpp.

#pragma once

#include <QString>
#include <QVariant>
#include <QVariantMap>
#include <vector>

#include "imgsli/contracts/plugin_contract.h"

namespace imgsli::app {

class Store;

class PluginRegistry final {
 public:
  static PluginRegistry& instance();

  const std::vector<imgsli::contracts::PluginContract*>& plugins() const {
    return plugins_;
  }

  imgsli::contracts::PluginContract* find(const QString& pluginId) const;

  /// Forward `callService` to the first plugin that claims to provide it.
  /// Returns an invalid QVariant when no plugin handles `serviceId`.
  QVariant callService(const QString& serviceId, const QVariantMap& args);

  /// Activation gate — pass the host Store once all plugins are loaded.
  void activateAll(Store* store);
  void deactivateAll();

  void registerPlugin(imgsli::contracts::PluginContract* plugin);

 private:
  PluginRegistry() = default;
  PluginRegistry(const PluginRegistry&) = delete;
  PluginRegistry& operator=(const PluginRegistry&) = delete;

  std::vector<imgsli::contracts::PluginContract*> plugins_;
  bool activated_ = false;
};

class PluginAutoRegister final {
 public:
  explicit PluginAutoRegister(imgsli::contracts::PluginContract* plugin) {
    PluginRegistry::instance().registerPlugin(plugin);
  }
};

#define IMGSLI_REGISTER_PLUGIN(Type)                                         \
  static ::imgsli::app::PluginAutoRegister _imgsli_plugin_register_##Type(    \
      new Type)

}  // namespace imgsli::app
