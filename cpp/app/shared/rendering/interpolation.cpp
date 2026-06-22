#include "shared/rendering/interpolation.h"

namespace imgsli::app::shared::rendering {

QString effectiveMainInterpolation(const QString& viewportValue) {
  if (!viewportValue.isEmpty()) {
    return viewportValue;
  }
  return QStringLiteral("BILINEAR");
}

QString effectiveExportInterpolation(const QString& viewportValue) {
  QString method = effectiveMainInterpolation(viewportValue);
  if (method.isEmpty()) {
    method = QStringLiteral("LANCZOS");
  }
  method = method.toUpper();
  if (method == QStringLiteral("NEAREST")) {
    return QStringLiteral("LANCZOS");
  }
  return method;
}

}  // namespace imgsli::app::shared::rendering
