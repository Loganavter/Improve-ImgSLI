#include "shared/image_processing/qt_conversion.h"

namespace imgsli::app::shared::image_processing {

QImage toRgba8888(const QImage& image) {
  if (image.isNull()) {
    return image;
  }
  if (image.format() == QImage::Format_RGBA8888) {
    return image;
  }
  return image.convertToFormat(QImage::Format_RGBA8888);
}

QPixmap toRgba8888Pixmap(const QImage& image, bool copy) {
  QImage normalised = toRgba8888(image);
  if (normalised.isNull()) {
    return {};
  }
  QPixmap pix = QPixmap::fromImage(normalised);
  return copy ? pix.copy() : pix;
}

}  // namespace imgsli::app::shared::image_processing
