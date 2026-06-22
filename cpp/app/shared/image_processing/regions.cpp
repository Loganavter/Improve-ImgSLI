#include "shared/image_processing/regions.h"

#include <algorithm>
#include <cmath>

namespace imgsli::app::shared::image_processing {

std::vector<UniformTileGrid::Tile> UniformTileGrid::tiles() const {
  std::vector<Tile> out;
  out.reserve(static_cast<std::size_t>(rows * columns));
  const int padW = paddedWidth();
  const int padH = paddedHeight();
  for (int row = 0; row < rows; ++row) {
    for (int col = 0; col < columns; ++col) {
      const int left = col * tileWidth;
      const int top = row * tileHeight;
      out.push_back(Tile{row, col,
                         ImageRegion{left, top,
                                     std::min(tileWidth, padW - left),
                                     std::min(tileHeight, padH - top)}});
    }
  }
  return out;
}

namespace {

int ceilDiv(int a, int b) {
  return static_cast<int>(std::ceil(static_cast<double>(a) / static_cast<double>(b)));
}

}  // namespace

UniformTileGrid buildUniformTileGrid(int totalWidth, int totalHeight,
                                     int maxTileWidth, int maxTileHeight,
                                     int minTilesPerAxis) {
  const int sw = std::max(1, totalWidth);
  const int sh = std::max(1, totalHeight);
  const int mtw = std::max(1, maxTileWidth);
  const int mth = std::max(1, maxTileHeight > 0 ? maxTileHeight : maxTileWidth);
  const int sm = std::max(1, minTilesPerAxis);

  const int cols = std::max(sm, ceilDiv(sw, mtw));
  const int rows = std::max(sm, ceilDiv(sh, mth));
  return UniformTileGrid{sw, sh, ceilDiv(sw, cols), ceilDiv(sh, rows), cols, rows};
}

UniformTileGrid buildSquareTileGrid(int totalWidth, int totalHeight,
                                    int maxTileExtent, int minTilesPerAxis) {
  const int sw = std::max(1, totalWidth);
  const int sh = std::max(1, totalHeight);
  const int me = std::max(1, maxTileExtent);
  const int sm = std::max(1, minTilesPerAxis);
  const int divisions = std::max(sm, ceilDiv(std::max(sw, sh), me));
  return UniformTileGrid{sw, sh, ceilDiv(sw, divisions), ceilDiv(sh, divisions),
                         divisions, divisions};
}

QRectF computeCenteredBox(int width, int height, double centerX, double centerY,
                          double boxWidth, double boxHeight) {
  const double sw = std::max(1.0, static_cast<double>(width));
  const double sh = std::max(1.0, static_cast<double>(height));
  const double bw = std::clamp(boxWidth, 1.0, sw);
  const double effectiveBoxH = boxHeight > 0.0 ? boxHeight : boxWidth;
  const double bh = std::clamp(effectiveBoxH, 1.0, sh);
  const double halfW = bw / 2.0;
  const double halfH = bh / 2.0;
  const double left =
      std::min(std::max(0.0, centerX - halfW), std::max(0.0, sw - bw));
  const double top =
      std::min(std::max(0.0, centerY - halfH), std::max(0.0, sh - bh));
  return QRectF(left, top, bw, bh);
}

}  // namespace imgsli::app::shared::image_processing
