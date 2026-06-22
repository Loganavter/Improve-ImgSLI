// Export plugin — service surface registration only.
//
// Per-service implementations live in `services/`:
//   * image_export.{h,cpp}   — decode_image, save_image
//   * canvas_export.{h,cpp}  — save_canvas (orchestrates offscreen render)
//
// This mirrors `src/plugins/export/services/{image_export,gpu_export*}.py`.

#include <QString>
#include <QStringList>
#include <QVariant>
#include <QVariantMap>

#include "core/plugin_registry.h"
#include "imgsli/contracts/plugin_contract.h"
#include "plugins/export/services/canvas_export.h"
#include "plugins/export/services/image_export.h"

namespace imgsli::app {
namespace {

class ExportPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override { return QStringLiteral("export"); }
  QString displayName() const override { return QStringLiteral("Export"); }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {
        QStringLiteral("export.save_image"),
        QStringLiteral("export.decode_image"),
        QStringLiteral("export.save_canvas"),
    };
    def.translationNamespaces = {QStringLiteral("export")};
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    return serviceId == QStringLiteral("export.save_image") ||
           serviceId == QStringLiteral("export.decode_image") ||
           serviceId == QStringLiteral("export.save_canvas");
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    if (serviceId == QStringLiteral("export.save_image")) {
      return export_services::saveImage(args);
    }
    if (serviceId == QStringLiteral("export.decode_image")) {
      return QVariant::fromValue(export_services::decodeImage(args));
    }
    if (serviceId == QStringLiteral("export.save_canvas")) {
      return export_services::saveCanvas(args);
    }
    return {};
  }
};

IMGSLI_REGISTER_PLUGIN(ExportPlugin);

}  // namespace
}  // namespace imgsli::app
