#pragma once

#include "sli/toolkit/buttons/layers/layer.h"

namespace sli::toolkit::buttons {

class StrikethroughLayer final : public Layer {
 public:
  LayerScope scope() const override { return LayerScope::Widget; }
  bool applies(const DrawContext& ctx) const override;
  void draw(const DrawContext& ctx, const Theme& theme) const override;
};

}  // namespace sli::toolkit::buttons
