#include "shared/image_processing/resize.h"

namespace imgsli::app::shared::image_processing {

Qt::TransformationMode interpolationToTransformMode(const QString& methodName) {
  const QString name = methodName.toUpper();
  if (name == QStringLiteral("NEAREST")) {
    return Qt::FastTransformation;
  }
  return Qt::SmoothTransformation;
}

QImage resampleImage(const QImage& image, const QSize& targetSize,
                     const QString& methodName) {
  if (image.isNull() || targetSize.isEmpty()) {
    return image;
  }
  if (image.size() == targetSize) {
    return image;
  }
  return image.scaled(targetSize, Qt::IgnoreAspectRatio,
                      interpolationToTransformMode(methodName));
}

}  // namespace imgsli::app::shared::image_processing
