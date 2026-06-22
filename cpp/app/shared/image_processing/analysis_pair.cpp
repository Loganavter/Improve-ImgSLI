#include "shared/image_processing/analysis_pair.h"

#include "shared/image_processing/qt_conversion.h"

#include <algorithm>

namespace imgsli::app::shared::image_processing {

AnalysisPair prepareAnalysisPair(const QImage& img1, const QImage& img2,
                                 int maxExtent) {
  if (img1.isNull() || img2.isNull()) {
    return AnalysisPair{img1, img2, false};
  }
  int targetW = std::max(img1.width(), img2.width());
  int targetH = std::max(img1.height(), img2.height());
  if (maxExtent > 0) {
    const double ratio =
        std::min(1.0, static_cast<double>(maxExtent) /
                          static_cast<double>(std::max(targetW, targetH)));
    targetW = std::max(1, static_cast<int>(targetW * ratio));
    targetH = std::max(1, static_cast<int>(targetH * ratio));
  }
  const QSize target(targetW, targetH);
  auto resample = [&](const QImage& img) {
    QImage scaled = img.size() == target
                        ? img
                        : img.scaled(target, Qt::IgnoreAspectRatio,
                                     Qt::SmoothTransformation);
    return toRgba8888(scaled);
  };
  return AnalysisPair{resample(img1), resample(img2), true};
}

}  // namespace imgsli::app::shared::image_processing
