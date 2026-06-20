// Phase 5: settings plugin.
//
// Most of the settings work landed in Phase 4 (SettingsDialog,
// SettingsApplicationService, Rust-side view-model). This plugin glues
// it into the registry so dialog access and the settings-apply service
// flow through the same PluginRegistry::callService surface as every
// other plugin. The plugin owns no widgets — the dialog is constructed
// on demand by the host.

#include <QString>
#include <QVariant>
#include <QVariantMap>

#include "imgsli/contracts/plugin_contract.h"
#include "plugin_registry.h"

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
    };
    def.translationNamespaces = {QStringLiteral("settings")};
    return def;
  }
};

IMGSLI_REGISTER_PLUGIN(SettingsPlugin);

}  // namespace
}  // namespace imgsli::app
