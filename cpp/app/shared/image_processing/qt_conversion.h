#pragma once

#include <QImage>
#include <QPixmap>

namespace imgsli::app::shared::image_processing {

// Coerces an arbitrary `QImage` to `Format_RGBA8888` (the format the QRhi
// canvas pipeline consumes). Calls are a no-op when the input already matches.
//
// The Python module also held `pil_to_qimage_zero_copy` / `_qpixmap_optimized`,
// which served PIL→Qt conversion. The C++ shell never owns PIL buffers — every
// image lives as a `QImage` from the moment it leaves QtConcurrent — so the
// PIL bridge is intentionally not ported. The remaining surface is the
// format-normalisation helper used by export and analysis paths.
QImage toRgba8888(const QImage& image);

QPixmap toRgba8888Pixmap(const QImage& image, bool copy = false);

}  // namespace imgsli::app::shared::image_processing
