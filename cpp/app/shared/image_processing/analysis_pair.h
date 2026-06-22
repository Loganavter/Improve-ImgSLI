#pragma once

#include <QImage>

namespace imgsli::app::shared::image_processing {

// POD result of `prepareAnalysisPair`. The two images are aligned to a shared
// size and converted to `Format_RGBA8888`. `valid` is false if either input is
// null or has an empty size.
struct AnalysisPair {
  QImage image1;
  QImage image2;
  bool valid = false;
};

// Mirror of Python `shared.image_processing.analysis_pair.prepare_analysis_pair`.
// Aligns `img1` / `img2` to one shared size (the larger of each axis, clamped
// to `maxExtent` when non-zero), then normalises both to `Format_RGBA8888` so
// PSNR/SSIM/diff metrics consume bit-equivalent buffers.
AnalysisPair prepareAnalysisPair(const QImage& img1, const QImage& img2,
                                 int maxExtent = 0);

}  // namespace imgsli::app::shared::image_processing
