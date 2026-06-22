#pragma once

#include <QImage>
#include <QSize>
#include <Qt>

namespace imgsli::app::shared::image_processing {

// Resolves an interpolation method name (`BILINEAR`, `BICUBIC`, `LANCZOS`,
// `NEAREST`) into the closest `Qt::TransformationMode`. Qt only exposes two
// modes (fast / smooth), so this is a coarse but stable mapping that mirrors
// the Python `resample_image` defaults used by the export/preview paths.
Qt::TransformationMode interpolationToTransformMode(const QString& methodName);

// Resamples `image` to `targetSize` using the interpolation method name
// from the viewport / settings (case-insensitive, defaults to LANCZOS).
QImage resampleImage(const QImage& image, const QSize& targetSize,
                     const QString& methodName = QStringLiteral("LANCZOS"));

}  // namespace imgsli::app::shared::image_processing
