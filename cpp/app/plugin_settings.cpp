// Phase 5: settings plugin.
//
// Most of the settings work landed in Phase 4 (SettingsDialog,
// SettingsApplicationService, Rust-side view-model). This plugin glues
// it into the registry so dialog access and the settings-apply service
// flow through the same PluginRegistry::callService surface as every
// other plugin. The plugin owns no widgets — the dialog is constructed
// on demand by the host.

#include <QPointer>
#include <QString>
#include <QStringList>
#include <QVariant>
#include <QVariantMap>

#include "imgsli/contracts/plugin_contract.h"
#include "plugin_registry.h"
#include "settings_application_service.h"

namespace imgsli::app {
namespace {

class SettingsPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override { return QStringLiteral("settings"); }
  QString displayName() const override { return QStringLiteral("Settings"); }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {
        QStringLiteral("settings.open_dialog"),
        QStringLiteral("settings.apply_dialog_diff"),
        QStringLiteral("settings.bind_service"),
    };
    def.translationNamespaces = {QStringLiteral("settings")};
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    return serviceId == QStringLiteral("settings.apply_dialog_diff") ||
           serviceId == QStringLiteral("settings.bind_service");
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    if (serviceId == QStringLiteral("settings.bind_service")) {
      // Late binding — the host constructs the SettingsApplicationService
      // after the QSettings instance is ready and registers it here.
      service_ =
          args.value(QStringLiteral("service"))
              .value<SettingsApplicationService*>();
      return service_ != nullptr;
    }
    if (serviceId == QStringLiteral("settings.apply_dialog_diff")) {
      if (service_.isNull()) {
        return 0;
      }
      const QString prev = args.value(QStringLiteral("prev")).toString();
      const QString next = args.value(QStringLiteral("next")).toString();
      return service_->apply(prev, next);
    }
    return {};
  }

 private:
  QPointer<SettingsApplicationService> service_;
};

IMGSLI_REGISTER_PLUGIN(SettingsPlugin);

}  // namespace
}  // namespace imgsli::app
