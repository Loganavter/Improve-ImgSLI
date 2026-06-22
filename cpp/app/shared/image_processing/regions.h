#pragma once

#include <QRectF>
#include <vector>

namespace imgsli::app::shared::image_processing {

// POD mirror of Python `shared.image_processing.regions.ImageRegion`.
struct ImageRegion {
  int left = 0;
  int top = 0;
  int width = 0;
  int height = 0;
  int right() const noexcept { return left + width; }
  int bottom() const noexcept { return top + height; }
};

// Uniform-tile-grid descriptor + iterator. Mirrors Python `UniformTileGrid`.
struct UniformTileGrid {
  int totalWidth = 0;
  int totalHeight = 0;
  int tileWidth = 0;
  int tileHeight = 0;
  int columns = 0;
  int rows = 0;

  int paddedWidth() const noexcept { return tileWidth * columns; }
  int paddedHeight() const noexcept { return tileHeight * rows; }

  struct Tile {
    int row;
    int col;
    ImageRegion region;
  };

  // Enumerates all tiles in row-major order; tile sizes shrink at the right
  // and bottom edges if the padded grid overshoots the totals.
  std::vector<Tile> tiles() const;
};

UniformTileGrid buildUniformTileGrid(int totalWidth, int totalHeight,
                                     int maxTileWidth,
                                     int maxTileHeight = 0,
                                     int minTilesPerAxis = 1);

UniformTileGrid buildSquareTileGrid(int totalWidth, int totalHeight,
                                    int maxTileExtent,
                                    int minTilesPerAxis = 1);

// Centred box clamped to the [(0,0), (width, height)] surface. Mirrors Python
// `compute_centered_box`. `boxHeight <= 0` means «use boxWidth for both».
QRectF computeCenteredBox(int width, int height, double centerX, double centerY,
                          double boxWidth, double boxHeight = 0.0);

}  // namespace imgsli::app::shared::image_processing
