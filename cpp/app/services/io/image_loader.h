#pragma once

#include <QImage>
#include <QString>

namespace imgsli::app::services::io {

struct LoadImageResult {
  QImage image;
  QString error;
  bool ok() const noexcept { return !image.isNull(); }
};

// Loads `path` into a `Format_RGBA8888` `QImage`. If `autoCropBlackBorders`
// is set, the surrounding (0, 0, 0, *) frame is trimmed. The progressive /
// preview-then-full pipeline lives in Python's `progressive_loader.py`;
// in C++ the equivalent two-stage decode is driven by the comparison
// plugin's QtConcurrent worker (see `plugins/comparison/use_cases/loading.cpp`).
// This service is the synchronous one-shot path used by CLI tools and
// non-interactive snapshots.
LoadImageResult loadImage(const QString& path, bool autoCropBlackBorders = false);

// Returns a copy of `image` with surrounding fully-transparent or fully-black
// rows/columns removed. Mirrors Python `crop_black_borders` (RGBA pixel sum
// threshold). Returns the input unchanged if nothing was trimmed.
QImage cropBlackBorders(const QImage& image);

}  // namespace imgsli::app::services::io
