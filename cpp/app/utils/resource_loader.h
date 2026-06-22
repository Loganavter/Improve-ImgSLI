#pragma once

#include <QFont>
#include <QPoint>
#include <QRect>
#include <QSize>
#include <QString>

#include <cmath>
#include <functional>

namespace imgsli::app::utils {

inline QRect safeRect(double x, double y, double w, double h) {
  return QRect(static_cast<int>(std::round(x)), static_cast<int>(std::round(y)),
               static_cast<int>(std::round(w)),
               static_cast<int>(std::round(h)));
}

inline QPoint safePoint(double x, double y) {
  return QPoint(static_cast<int>(std::round(x)),
                static_cast<int>(std::round(y)));
}

// Resolve a project-relative resource path. Looks up `IMGSLI_RESOURCE_ROOT`
// env var first (set by CMake at build time), falls back to the binary
// directory.
QString resourcePath(const QString& relativePath);

// Mirrors Python `truncate_text(...)`. `getSize(text, font)` returns the
// pixel width of `text` rendered in `font`. The function finds the longest
// prefix that fits in `availableWidth` and appends one of "...", "..", "."
// as ellipsis. Pure utility, no Qt widgets touched.
using GetSizeFn = std::function<QSize(const QString&, const QFont&)>;

QString truncateText(const QString& text, int availableWidth, int maxLen,
                     const QFont& font, const GetSizeFn& getSize);

// Bounded-contain scaling: smaller of the two source images dictates the
// scale factor that keeps both inside (target_w, target_h). Mirrors Python
// `get_scaled_pixmap_dimensions`.
QSize scaledPixmapDimensions(const QSize& image1, const QSize& image2,
                             int targetWidth, int targetHeight);

}  // namespace imgsli::app::utils
