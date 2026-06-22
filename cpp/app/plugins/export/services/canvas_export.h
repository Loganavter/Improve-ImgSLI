#pragma once

#include <QVariantMap>

// Mirrors src/plugins/export/services/{gpu_export,gpu_export_proxy}.py —
// orchestrates an offscreen render of the active canvas and saves the
// result through image_export.

namespace imgsli::app::export_services {

QVariantMap saveCanvas(const QVariantMap& args);

}  // namespace imgsli::app::export_services
