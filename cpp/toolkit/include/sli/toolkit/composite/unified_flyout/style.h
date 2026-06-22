#pragma once

namespace sli::toolkit::unified_flyout {

// Python: SHADOW_RADIUS = 24 in _UnifiedFlyoutStyleMixin.
constexpr int kShadowRadius = 24;

struct FlyoutStyle {
  int cornerRadius = 8;
  int itemHeight = 32;
  int itemPadding = 8;
  int panelMargin = 4;
  int dividerHeight = 1;
};

inline const FlyoutStyle& defaultStyle() {
  static const FlyoutStyle s{};
  return s;
}

}  // namespace sli::toolkit::unified_flyout
