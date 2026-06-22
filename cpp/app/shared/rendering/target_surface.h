#pragma once

#include <cstdint>
#include <optional>

namespace imgsli::app::shared::rendering {

// POD mirror of Python `shared.rendering.target_surface.TargetSurfaceSpec`.
struct TargetSurfaceSpec {
  int width = 0;
  int height = 0;
  // RGBA channels in [0, 255]. Absent means «leave surface transparent /
  // do not paint a background fill».
  std::optional<std::uint32_t> fillRgba;
  double outputScale = 1.0;
  bool preserveZoom = false;
  bool clipOverlaysToImageBounds = false;
};

}  // namespace imgsli::app::shared::rendering
