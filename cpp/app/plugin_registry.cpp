#include "plugin_registry.h"

namespace imgsli::app {

PluginRegistry& PluginRegistry::instance() {
  static PluginRegistry registry;
  return registry;
}

void PluginRegistry::registerPlugin(
    imgsli::contracts::PluginContract* plugin) {
  if (plugin == nullptr) {
    return;
  }
  plugins_.push_back(plugin);
}

imgsli::contracts::PluginContract* PluginRegistry::find(
    const QString& pluginId) const {
  for (auto* plugin : plugins_) {
    if (plugin != nullptr && plugin->pluginId() == pluginId) {
      return plugin;
    }
  }
  return nullptr;
}

QVariant PluginRegistry::callService(const QString& serviceId,
                                     const QVariantMap& args) {
  for (auto* plugin : plugins_) {
    if (plugin != nullptr && plugin->providesService(serviceId)) {
      return plugin->callService(serviceId, args);
    }
  }
  return {};
}

void PluginRegistry::activateAll(Store* store) {
  if (activated_) {
    return;
  }
  for (auto* plugin : plugins_) {
    if (plugin != nullptr) {
      plugin->onActivate(store);
    }
  }
  activated_ = true;
}

void PluginRegistry::deactivateAll() {
  if (!activated_) {
    return;
  }
  for (auto* plugin : plugins_) {
    if (plugin != nullptr) {
      plugin->onDeactivate();
    }
  }
  activated_ = false;
}

}  // namespace imgsli::app
