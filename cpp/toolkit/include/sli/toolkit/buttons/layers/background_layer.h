#pragma once

#include "sli/toolkit/buttons/layers/layer.h"

namespace sli::toolkit::buttons {

class BackgroundLayer final : public Layer {
 public:
  void draw(const DrawContext& ctx, const Theme& theme) const override;
};

}  // namespace sli::toolkit::buttons
