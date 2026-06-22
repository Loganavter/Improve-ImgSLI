#include "sli/toolkit/buttons/specs.h"

namespace sli::toolkit::buttons {

ContentSpec ContentSpec::fromRegion(const ButtonRegion& region) {
  ContentSpec spec;
  spec.icon = region.icon;
  spec.iconChecked = region.iconChecked;
  spec.text = region.text;
  if (region.rows.has_value()) {
    spec.rows = *region.rows;
  }
  return spec;
}

RegionStyle RegionStyle::fromRegion(const ButtonRegion& region) {
  RegionStyle style;
  style.variant = region.variant;
  style.customBgColor = region.customBgColor;
  style.overrideBgColor = region.overrideBgColor;
  style.overrideBorderColor = region.overrideBorderColor;
  style.showUnderline = region.showUnderline;
  style.underlineColor = region.underlineColor;
  style.underlineThickness = region.underlineThickness;
  style.iconSizePx = region.iconSizePx;
  style.showStrikeThrough = region.showStrikeThrough;
  return style;
}

RegionSpec RegionSpec::fromRegion(const ButtonRegion& region) {
  RegionSpec spec;
  spec.id = region.id;
  spec.content = ContentSpec::fromRegion(region);
  spec.style = RegionStyle::fromRegion(region);
  spec.weight = region.weight;
  spec.enabled = region.enabled;
  spec.badge = region.badge;
  spec.cursor = region.cursor;
  spec.rectFn = region.rectFn;
  spec.pathFn = region.pathFn;
  spec.zIndex = region.zIndex;

  spec.behaviors.push_back(clickBehavior());
  if (region.toggle) {
    spec.behaviors.push_back(toggleBehavior());
  }
  if (region.scrollable.has_value()) {
    spec.behaviors.push_back(
        scrollBehavior(region.scrollable->first, region.scrollable->second));
  }
  if (region.longPress) {
    spec.behaviors.push_back(longPressBehavior(region.longPressMs));
  }
  if (region.menu.has_value()) {
    spec.behaviors.push_back(menuBehavior(*region.menu));
  }
  return spec;
}

ButtonRegion RegionSpec::toRegion() const {
  ButtonRegion region;
  region.id = id;
  region.weight = weight;
  region.icon = content.icon;
  region.iconChecked = content.iconChecked;
  region.text = content.text;
  if (!content.rows.empty()) {
    region.rows = content.rows;
  }
  region.badge = badge;
  region.variant = style.variant;
  region.customBgColor = style.customBgColor;
  region.overrideBgColor = style.overrideBgColor;
  region.overrideBorderColor = style.overrideBorderColor;
  region.showUnderline = style.showUnderline;
  region.underlineColor = style.underlineColor;
  region.underlineThickness = style.underlineThickness;
  region.iconSizePx = style.iconSizePx;
  region.showStrikeThrough = style.showStrikeThrough;
  region.enabled = enabled;
  region.cursor = cursor;
  region.rectFn = rectFn;
  region.pathFn = pathFn;
  region.zIndex = zIndex;

  for (const auto& behavior : behaviors) {
    switch (behavior.kind) {
      case BehaviorKind::Toggle:
        region.toggle = true;
        break;
      case BehaviorKind::LongPress:
        region.longPress = true;
        region.longPressMs = behavior.longPressDelayMs;
        break;
      case BehaviorKind::Scroll:
        region.scrollable = std::pair<int, int>{behavior.scrollMin,
                                                behavior.scrollMax};
        break;
      case BehaviorKind::Menu:
        region.menu = behavior.menuItems;
        break;
      case BehaviorKind::Click:
        break;
    }
  }
  return region;
}

ButtonSpec ButtonSpec::fromRegions(const std::vector<ButtonRegion>& regions,
                                   const ButtonSpecArgs& args) {
  ButtonSpec spec;
  spec.regions.reserve(regions.size());
  for (const auto& region : regions) {
    spec.regions.push_back(RegionSpec::fromRegion(region));
  }
  spec.split = args.split ? args.split : std::make_shared<SingleRegionSplit>();
  spec.divider = args.divider;
  spec.shape = args.shape.value_or(ShapeSpec{});
  spec.variant = args.variant;
  spec.density = args.density;
  spec.deferClick = args.deferClick;
  spec.wheelRequiresFocus = args.wheelRequiresFocus;
  return spec;
}

std::vector<ButtonRegion> ButtonSpec::toRegions() const {
  std::vector<ButtonRegion> out;
  out.reserve(regions.size());
  for (const auto& region : regions) {
    out.push_back(region.toRegion());
  }
  return out;
}

}  // namespace sli::toolkit::buttons
