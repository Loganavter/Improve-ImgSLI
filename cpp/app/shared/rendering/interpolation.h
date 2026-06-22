#pragma once

#include <QString>

namespace imgsli::app::shared::rendering {

// Normalises the viewport's interpolation method. Mirrors Python
// `shared.rendering.interpolation`:
//   * `effectiveMainInterpolation` returns the raw value (defaults to
//     `BILINEAR`).
//   * `effectiveExportInterpolation` upper-cases the result and substitutes
//     `LANCZOS` for `NEAREST` — exporting at NEAREST is almost always
//     unintended.
QString effectiveMainInterpolation(const QString& viewportValue);
QString effectiveExportInterpolation(const QString& viewportValue);

}  // namespace imgsli::app::shared::rendering
