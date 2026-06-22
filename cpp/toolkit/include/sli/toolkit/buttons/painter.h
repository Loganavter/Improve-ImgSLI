#pragma once

#include <memory>
#include <vector>

#include "sli/toolkit/buttons/layers/layer.h"

namespace sli::toolkit {
class Theme;
}

namespace sli::toolkit::buttons {

struct DrawContext;

class Painter {
 public:
  explicit Painter(const Theme& theme,
                   std::vector<std::unique_ptr<Layer>> layers = {});
  void paint(const DrawContext& ctx) const;

  static std::vector<std::unique_ptr<Layer>> defaultLayers();

 private:
  const Theme& theme_;
  std::vector<std::unique_ptr<Layer>> layers_;
};

}  // namespace sli::toolkit::buttons
