// Phase 5: export plugin.
//
// Provides image-export services backed by Qt's QImage::save plus the
// Rust image decoder. Only the still-image side is ported here; the
// video-export pipeline depends on ffmpeg-process orchestration that
// belongs with the video editor plugin.
//
// Service surface (call via PluginRegistry::callService):
//   * "export.save_image"
//       args: { path: QString, image: QImage, format: QString,
//               quality: int (0..100, optional) }
//       returns: bool — success.
//   * "export.decode_image"
//       args: { path: QString }
//       returns: QImage — decoded RGBA8 via Rust core, null on failure.

#include <QByteArray>
#include <QFileInfo>
#include <QImage>
#include <QImageWriter>
#include <QString>
#include <QVariant>
#include <QVariantMap>

#include <exception>
#include <string>

#include "imgsli/contracts/plugin_contract.h"
#include "imgsli_core_bridge/bridge.h"
#include "plugin_registry.h"

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
    };
    def.translationNamespaces = {QStringLiteral("export")};
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    return serviceId == QStringLiteral("export.save_image") ||
           serviceId == QStringLiteral("export.decode_image");
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    if (serviceId == QStringLiteral("export.save_image")) {
      return saveImage(args);
    }
    if (serviceId == QStringLiteral("export.decode_image")) {
      return QVariant::fromValue(decodeImage(args));
    }
    return {};
  }

 private:
  static QImage decodeImage(const QVariantMap& args) {
    const QString path = args.value(QStringLiteral("path")).toString();
    if (path.isEmpty()) {
      return {};
    }
    const QByteArray utf8 = path.toUtf8();
    try {
      const auto decoded = imgsli::decode_image_rgba8(
          std::string(utf8.constData(),
                      static_cast<std::size_t>(utf8.size())));
      if (decoded.width == 0 || decoded.height == 0 ||
          decoded.pixels.empty()) {
        return {};
      }
      const auto* bytes =
          reinterpret_cast<const uchar*>(decoded.pixels.data());
      return QImage(bytes, static_cast<int>(decoded.width),
                    static_cast<int>(decoded.height),
                    static_cast<qsizetype>(decoded.width) * 4,
                    QImage::Format_RGBA8888)
          .copy();
    } catch (const std::exception&) {
      return {};
    }
  }

  static bool saveImage(const QVariantMap& args) {
    const QString path = args.value(QStringLiteral("path")).toString();
    const QImage image = args.value(QStringLiteral("image")).value<QImage>();
    if (path.isEmpty() || image.isNull()) {
      return false;
    }
    QByteArray format =
        args.value(QStringLiteral("format")).toString().toUtf8();
    if (format.isEmpty()) {
      format = QFileInfo(path).suffix().toUtf8();
    }
    QImageWriter writer(path, format);
    if (args.contains(QStringLiteral("quality"))) {
      writer.setQuality(args.value(QStringLiteral("quality")).toInt());
    }
    return writer.write(image);
  }
};

IMGSLI_REGISTER_PLUGIN(ExportPlugin);

}  // namespace
}  // namespace imgsli::app
