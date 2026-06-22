#include <QPointer>
#include <QVariantMap>

#include "plugins/help/dialog.h"
#include "imgsli/contracts/plugin_contract.h"
#include "core/plugin_registry.h"

namespace imgsli::app {
namespace {

class HelpPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override { return QStringLiteral("help"); }
  QString displayName() const override { return QStringLiteral("Help"); }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {QStringLiteral("help.show"),
                      QStringLiteral("help.set_language"),
                      QStringLiteral("help.section_count")};
    def.translationNamespaces = {QStringLiteral("help")};
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    return serviceId == QStringLiteral("help.show") ||
           serviceId == QStringLiteral("help.set_language") ||
           serviceId == QStringLiteral("help.section_count");
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    const QString root =
        args.value(QStringLiteral("root"), QStringLiteral(IMGSLI_HELP_ROOT))
            .toString();
    if (serviceId == QStringLiteral("help.set_language")) {
      language_ =
          args.value(QStringLiteral("language"), QStringLiteral("en")).toString();
      if (!dialog_.isNull()) {
        dialog_->setLanguage(language_);
      }
      return true;
    }
    const QString language =
        args.value(QStringLiteral("language"), language_).toString();
    auto* parent = qobject_cast<QWidget*>(
        args.value(QStringLiteral("parent")).value<QObject*>());
    if (dialog_.isNull()) {
      dialog_ = new HelpDialog(root, language, parent);
      dialog_->setAttribute(Qt::WA_DeleteOnClose, true);
    } else {
      dialog_->setLanguage(language);
    }
    language_ = language;
    if (serviceId == QStringLiteral("help.section_count")) {
      return dialog_->sectionCount();
    }
    dialog_->show();
    dialog_->raise();
    dialog_->activateWindow();
    return true;
  }

 private:
  QPointer<HelpDialog> dialog_;
  QString language_ = QStringLiteral("en");
};

IMGSLI_REGISTER_PLUGIN(HelpPlugin);

}  // namespace
}  // namespace imgsli::app
