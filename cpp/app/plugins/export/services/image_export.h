#pragma once

#include <QImage>
#include <QVariantMap>

// Mirrors src/plugins/export/services/image_export.py — the QImage I/O
// layer. Decode delegates to the Rust core; save uses QImageWriter.

namespace imgsli::app::export_services {

QImage decodeImage(const QVariantMap& args);
bool saveImage(const QVariantMap& args);

}  // namespace imgsli::app::export_services
