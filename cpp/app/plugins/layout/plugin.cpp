#include <QHash>
#include <QPointer>
#include <QSet>
#include <QVariantMap>
#include <QWidget>

#include "imgsli/contracts/plugin_contract.h"
#include "core/plugin_registry.h"

namespace imgsli::app {
namespace {

class LayoutPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override { return QStringLiteral("layout"); }
  QString displayName() const override { return QStringLiteral("Layout"); }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {QStringLiteral("layout.bind_controls"),
                      QStringLiteral("layout.apply_mode")};
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    return serviceId == QStringLiteral("layout.bind_controls") ||
           serviceId == QStringLiteral("layout.apply_mode");
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    if (serviceId == QStringLiteral("layout.bind_controls")) {
      controls_.clear();
      const QVariantMap controls =
          args.value(QStringLiteral("controls")).toMap();
      for (auto it = controls.cbegin(); it != controls.cend(); ++it) {
        if (auto* widget = qobject_cast<QWidget*>(it.value().value<QObject*>())) {
          controls_.insert(it.key(), widget);
        }
      }
      applyMode(args.value(QStringLiteral("mode"),
                           QStringLiteral("beginner")).toString());
      return controls_.size();
    }
    return applyMode(args.value(QStringLiteral("mode")).toString());
  }

 private:
  bool applyMode(QString mode) {
    static const QHash<QString, QSet<QString>> visible{
        {QStringLiteral("beginner"),
         {QStringLiteral("open"), QStringLiteral("split"),
          QStringLiteral("orientation"), QStringLiteral("magnifier"),
          QStringLiteral("guides"), QStringLiteral("settings"),
          QStringLiteral("help"), QStringLiteral("workspace"),
          QStringLiteral("split_label")}},
        {QStringLiteral("advanced"),
         {QStringLiteral("open"), QStringLiteral("split"),
          QStringLiteral("orientation"), QStringLiteral("magnifier"),
          QStringLiteral("guides"), QStringLiteral("paste"),
          QStringLiteral("settings"), QStringLiteral("help"),
          QStringLiteral("workspace"), QStringLiteral("theme"),
          QStringLiteral("theme_label"), QStringLiteral("split_label")}},
        {QStringLiteral("expert"),
         {QStringLiteral("open"), QStringLiteral("split"),
          QStringLiteral("orientation"), QStringLiteral("magnifier"),
          QStringLiteral("guides"), QStringLiteral("paste"),
          QStringLiteral("settings"), QStringLiteral("help"),
          QStringLiteral("workspace"), QStringLiteral("theme"),
          QStringLiteral("theme_label"), QStringLiteral("state"),
          QStringLiteral("state_label"), QStringLiteral("roundtrip"),
          QStringLiteral("roundtrip_label"), QStringLiteral("split_label")}},
        {QStringLiteral("minimal"),
         {QStringLiteral("open"), QStringLiteral("split"),
          QStringLiteral("orientation"), QStringLiteral("magnifier"),
          QStringLiteral("help"), QStringLiteral("split_label")}},
    };
    if (!visible.contains(mode)) {
      mode = QStringLiteral("beginner");
    }
    const QSet<QString>& active = visible.value(mode);
    for (auto it = controls_.cbegin(); it != controls_.cend(); ++it) {
      if (!it.value().isNull()) {
        it.value()->setVisible(active.contains(it.key()));
      }
    }
    currentMode_ = mode;
    return true;
  }

  QHash<QString, QPointer<QWidget>> controls_;
  QString currentMode_ = QStringLiteral("beginner");
};

IMGSLI_REGISTER_PLUGIN(LayoutPlugin);

}  // namespace
}  // namespace imgsli::app
