#include "services/io/image_loader.h"

#include "shared/image_processing/qt_conversion.h"

#include <QImageReader>

namespace imgsli::app::services::io {

namespace {

bool rowIsBlack(const QImage& image, int y) {
  for (int x = 0; x < image.width(); ++x) {
    const QRgb px = image.pixel(x, y);
    if (qAlpha(px) != 0 && (qRed(px) + qGreen(px) + qBlue(px)) != 0) {
      return false;
    }
  }
  return true;
}

bool columnIsBlack(const QImage& image, int x) {
  for (int y = 0; y < image.height(); ++y) {
    const QRgb px = image.pixel(x, y);
    if (qAlpha(px) != 0 && (qRed(px) + qGreen(px) + qBlue(px)) != 0) {
      return false;
    }
  }
  return true;
}

}  // namespace

QImage cropBlackBorders(const QImage& image) {
  if (image.isNull()) {
    return image;
  }
  const QImage rgba = shared::image_processing::toRgba8888(image);
  int top = 0;
  int bottom = rgba.height() - 1;
  int left = 0;
  int right = rgba.width() - 1;
  while (top < bottom && rowIsBlack(rgba, top)) ++top;
  while (bottom > top && rowIsBlack(rgba, bottom)) --bottom;
  while (left < right && columnIsBlack(rgba, left)) ++left;
  while (right > left && columnIsBlack(rgba, right)) --right;
  if (top == 0 && left == 0 && bottom == rgba.height() - 1 &&
      right == rgba.width() - 1) {
    return rgba;
  }
  const int width = right - left + 1;
  const int height = bottom - top + 1;
  if (width <= 0 || height <= 0) {
    return rgba;
  }
  return rgba.copy(left, top, width, height);
}

LoadImageResult loadImage(const QString& path, bool autoCropBlackBorders) {
  QImageReader reader(path);
  reader.setAutoTransform(true);
  QImage image = reader.read();
  if (image.isNull()) {
    return LoadImageResult{{}, reader.errorString()};
  }
  image = shared::image_processing::toRgba8888(image);
  if (autoCropBlackBorders) {
    image = cropBlackBorders(image);
  }
  return LoadImageResult{image, QString()};
}

}  // namespace imgsli::app::services::io
