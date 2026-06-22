#pragma once

#include "sli/toolkit/buttons/layers/layer.h"
#include "sli/toolkit/buttons/layers/ripple.h"

namespace sli::toolkit::buttons {

class RippleLayer final : public Layer {
 public:
  // Region-scoped: each region runs its own RippleEffect (Python
  // `self._region_ripple[region.id]`). The widget-scope-only path used
  // before forced every region to share a single effect and never fired
  // because the `_ripple` widget property was never set.
  LayerScope scope() const override { return LayerScope::Region; }
  bool applies(const DrawContext& ctx) const override;
  void draw(const DrawContext& ctx, const Theme& theme) const override;
};

}  // namespace sli::toolkit::buttons
