#include <QImage>
#include <QStringList>
#include <QVariantMap>

#include <cstdint>
#include <exception>
#include <string>

#include "imgsli/contracts/plugin_contract.h"
#include "imgsli_core_bridge/bridge.h"
#include "core/plugin_registry.h"

namespace imgsli::app {
namespace {

QImage rgbaImage(const imgsli::DecodedImage& decoded) {
  if (decoded.width == 0 || decoded.height == 0 || decoded.pixels.empty()) {
    return {};
  }
  return QImage(reinterpret_cast<const uchar*>(decoded.pixels.data()),
                static_cast<int>(decoded.width),
                static_cast<int>(decoded.height),
                static_cast<qsizetype>(decoded.width) * 4,
                QImage::Format_RGBA8888)
      .copy();
}

QImage normalized(const QVariantMap& args, const QString& key) {
  return args.value(key)
      .value<QImage>()
      .convertToFormat(QImage::Format_RGBA8888);
}

rust::Slice<const std::uint8_t> pixels(const QImage& image) {
  return {reinterpret_cast<const std::uint8_t*>(image.constBits()),
          static_cast<std::size_t>(image.sizeInBytes())};
}

class AnalysisPlugin final : public imgsli::contracts::PluginContract {
 public:
  QString pluginId() const override { return QStringLiteral("analysis"); }
  QString displayName() const override { return QStringLiteral("Analysis"); }

  imgsli::contracts::PluginDefinition definition() const override {
    imgsli::contracts::PluginDefinition def;
    def.id = pluginId();
    def.commandIds = {
        QStringLiteral("analysis.metrics"),
        QStringLiteral("analysis.diff"),
        QStringLiteral("analysis.channel"),
    };
    def.translationNamespaces = {QStringLiteral("analysis")};
    return def;
  }

  bool providesService(const QString& serviceId) const override {
    return serviceId == QStringLiteral("analysis.metrics") ||
           serviceId == QStringLiteral("analysis.diff") ||
           serviceId == QStringLiteral("analysis.channel");
  }

  QVariant callService(const QString& serviceId,
                       const QVariantMap& args) override {
    try {
      const QImage left = normalized(args, QStringLiteral("left"));
      if (left.isNull()) {
        return {};
      }
      if (serviceId == QStringLiteral("analysis.channel")) {
        const QString channel =
            args.value(QStringLiteral("channel"), QStringLiteral("RGB"))
                .toString();
        return QVariant::fromValue(rgbaImage(imgsli::analysis_channel_rgba8(
            pixels(left), left.width(), left.height(),
            channel.toStdString())));
      }

      const QImage right = normalized(args, QStringLiteral("right"));
      if (right.isNull() || left.size() != right.size()) {
        return {};
      }
      if (serviceId == QStringLiteral("analysis.metrics")) {
        const auto result = imgsli::analysis_metrics_rgba8(
            pixels(left), pixels(right), left.width(), left.height());
        return QVariantMap{{QStringLiteral("psnr"), result.psnr},
                           {QStringLiteral("ssim"), result.ssim}};
      }
      const QString mode = args.value(QStringLiteral("mode")).toString();
      const QString channel =
          args.value(QStringLiteral("channel"), QStringLiteral("RGB"))
              .toString();
      return QVariant::fromValue(rgbaImage(imgsli::analysis_diff_rgba8(
          pixels(left), pixels(right), left.width(), left.height(),
          mode.toStdString(), channel.toStdString())));
    } catch (const std::exception&) {
      return {};
    }
  }
};

IMGSLI_REGISTER_PLUGIN(AnalysisPlugin);

}  // namespace
}  // namespace imgsli::app
