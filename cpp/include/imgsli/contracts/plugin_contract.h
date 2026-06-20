// Plugin contract — C++ port of src/core/plugin_system/interfaces.py.
//
// In Python the plugin surface is split across IControllablePlugin /
// IUIPlugin / IServicePlugin / IRenderPlugin / ISessionPlugin. The
// C++ port collapses these into one interface — the granularity exists
// only because Python lacks multiple inheritance markers; with a single
// virtual interface we just leave the unused hooks as no-ops.
//
// Phase 5 uses static registration through PluginRegistry; dynamic
// loading via QPluginLoader can be added later if hot reload becomes
// a real need (see the Phase 5 section of CPP_RUST_MIGRATION.md).

#pragma once

#include <QString>
#include <QStringList>
#include <QVariant>
#include <QVariantMap>

namespace imgsli::app {
class Store;
}

namespace imgsli::contracts {

/// Declarative contribution descriptor — mirrors
/// `core.plugin_system.contributions.PluginDefinition`. Lets the registry
/// surface what a plugin offers without having to inspect each capability.
struct PluginDefinition {
  QString id;
  QStringList commandIds;
  QStringList queryIds;
  QStringList translationNamespaces;
  QStringList resourceNamespaces;
  QVariantMap metadata;
};

class PluginContract {
 public:
  virtual ~PluginContract() = default;

  /// Stable identifier, e.g. "comparison". Used as the registry key and
  /// the prefix for translation/resource namespaces.
  virtual QString pluginId() const = 0;

  /// Human-readable name (translated via i18n).
  virtual QString displayName() const = 0;

  /// Optional version string (semver). The registry surfaces it but does
  /// not enforce compatibility yet.
  virtual QString version() const { return QStringLiteral("0.1.0"); }

  /// Declarative descriptor used by the registry/UI for discovery. May
  /// reuse [pluginId] and translation namespaces.
  virtual PluginDefinition definition() const {
    PluginDefinition def;
    def.id = pluginId();
    return def;
  }

  /// Lifecycle — called once after the registry is fully populated and
  /// the host Store is available, and again on shutdown.
  virtual void onActivate(imgsli::app::Store* store) { (void)store; }
  virtual void onDeactivate() {}

  /// Optional service entry point. Plugins that expose host-side
  /// services (e.g. PNG export) can implement this; callers route via
  /// the registry's `callService` and check capabilities by id.
  virtual QVariant callService(const QString& serviceId,
                               const QVariantMap& args) {
    (void)serviceId;
    (void)args;
    return {};
  }

  virtual bool providesService(const QString& serviceId) const {
    (void)serviceId;
    return false;
  }
};

}  // namespace imgsli::contracts
