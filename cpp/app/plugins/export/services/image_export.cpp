#include "plugins/export/services/image_export.h"

#include <QByteArray>
#include <QFileInfo>
#include <QImageWriter>
#include <QString>

#include <exception>
#include <string>

#include "imgsli_core_bridge/bridge.h"

namespace imgsli::app::export_services {

QImage decodeImage(const QVariantMap& args) {
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
    const auto* bytes = reinterpret_cast<const uchar*>(decoded.pixels.data());
    return QImage(bytes, static_cast<int>(decoded.width),
                   static_cast<int>(decoded.height),
                   static_cast<qsizetype>(decoded.width) * 4,
                   QImage::Format_RGBA8888)
        .copy();
  } catch (const std::exception&) {
    return {};
  }
}

bool saveImage(const QVariantMap& args) {
  const QString path = args.value(QStringLiteral("path")).toString();
  const QImage image = args.value(QStringLiteral("image")).value<QImage>();
  if (path.isEmpty() || image.isNull()) {
    return false;
  }
  QByteArray format = args.value(QStringLiteral("format")).toString().toUtf8();
  if (format.isEmpty()) {
    format = QFileInfo(path).suffix().toUtf8();
  }
  QImageWriter writer(path, format);
  if (args.contains(QStringLiteral("quality"))) {
    writer.setQuality(args.value(QStringLiteral("quality")).toInt());
  }
  return writer.write(image);
}

}  // namespace imgsli::app::export_services
