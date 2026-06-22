#pragma once

namespace sli::toolkit {
class Theme;
}

namespace sli::toolkit::buttons {

struct DrawContext;

enum class LayerScope {
  Region,
  Widget,
};

class Layer {
 public:
  virtual ~Layer() = default;
  virtual LayerScope scope() const { return LayerScope::Region; }
  virtual bool applies(const DrawContext& ctx) const {
    (void)ctx;
    return true;
  }
  virtual void draw(const DrawContext& ctx, const Theme& theme) const = 0;
};

}  // namespace sli::toolkit::buttons
