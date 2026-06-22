#include "shared/image_processing/prescale.h"

#include <algorithm>

namespace imgsli::app::shared::image_processing {

QSize sharedPrescaleSize(const QSize& size1, const QSize& size2, int outputWidth,
                        int outputHeight) {
  if (size1.isEmpty() || size2.isEmpty() || outputWidth <= 0 || outputHeight <= 0) {
    return {};
  }
  const int srcW = std::max(size1.width(), size2.width());
  const int srcH = std::max(size1.height(), size2.height());
  const double ratio = std::min(static_cast<double>(outputWidth) / srcW,
                                static_cast<double>(outputHeight) / srcH);
  if (ratio >= 1.0) {
    return QSize(srcW, srcH);
  }
  return QSize(std::max(1, static_cast<int>(srcW * ratio)),
               std::max(1, static_cast<int>(srcH * ratio)));
}

std::pair<QImage, QImage> prescalePair(const QImage& img1, const QImage& img2,
                                       int outputWidth, int outputHeight,
                                       Qt::TransformationMode mode) {
  if (img1.isNull() || img2.isNull()) {
    return {img1, img2};
  }
  const QSize target =
      sharedPrescaleSize(img1.size(), img2.size(), outputWidth, outputHeight);
  if (!target.isValid()) {
    return {img1, img2};
  }
  auto fit = [&](const QImage& img) {
    if (img.size() == target) {
      return img;
    }
    return img.scaled(target, Qt::IgnoreAspectRatio, mode);
  };
  return {fit(img1), fit(img2)};
}

}  // namespace imgsli::app::shared::image_processing
