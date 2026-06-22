#pragma once

#include <QImage>
#include <QSize>
#include <Qt>

#include <utility>

namespace imgsli::app::shared::image_processing {

// Returns the shared target size for the pair, mirroring Python `prescale_pair`:
// the largest source dimensions are taken first and the output bound is applied
// to the union (so an extreme-aspect pair is not stomped by the smaller image).
// Returns an invalid `QSize()` if either source is empty.
QSize sharedPrescaleSize(const QSize& size1, const QSize& size2, int outputWidth,
                        int outputHeight);

// Convenience wrapper that resamples both images to the shared target size
// using QImage's transform. `mode` defaults to `SmoothTransformation`.
std::pair<QImage, QImage> prescalePair(
    const QImage& img1, const QImage& img2, int outputWidth, int outputHeight,
    Qt::TransformationMode mode = Qt::SmoothTransformation);

}  // namespace imgsli::app::shared::image_processing
