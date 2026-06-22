#include "sli/toolkit/buttons/painter.h"

#include "sli/toolkit/buttons/content/content.h"
#include "sli/toolkit/buttons/controller.h"
#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/buttons/layers/background_layer.h"
#include "sli/toolkit/buttons/layers/badge_layer.h"
#include "sli/toolkit/buttons/layers/content_layer.h"
#include "sli/toolkit/buttons/layers/divider_layer.h"
#include "sli/toolkit/buttons/layers/ripple_layer.h"
#include "sli/toolkit/buttons/layers/strikethrough_layer.h"
#include "sli/toolkit/buttons/layers/underline_layer.h"
#include "sli/toolkit/buttons/variants.h"

namespace sli::toolkit::buttons {

Painter::Painter(const Theme& theme, std::vector<std::unique_ptr<Layer>> layers)
    : theme_(theme),
      layers_(layers.empty() ? defaultLayers() : std::move(layers)) {}

std::vector<std::unique_ptr<Layer>> Painter::defaultLayers() {
  std::vector<std::unique_ptr<Layer>> layers;
  layers.push_back(std::make_unique<BackgroundLayer>());
  layers.push_back(std::make_unique<RippleLayer>());
  layers.push_back(std::make_unique<ContentLayer>());
  layers.push_back(std::make_unique<BadgeLayer>());
  layers.push_back(std::make_unique<UnderlineLayer>());
  layers.push_back(std::make_unique<DividerLayer>());
  layers.push_back(std::make_unique<StrikethroughLayer>());
  return layers;
}

void Painter::paint(const DrawContext& ctx) const {
  // Detect a multi-region controller via an opt-in widget property: any
  // QWidget can stash `buttonController` to expose its controller without
  // forcing toolkit consumers to subclass from a shared base. Single-region
  // widgets just leave the property unset and we take the fast path.
  ButtonController* controller = nullptr;
  if (ctx.widget != nullptr) {
    controller = ctx.widget->property("buttonController")
                     .value<ButtonController*>();
  }
  const bool multiRegion = controller != nullptr &&
                            controller->regions().size() > 1;

  if (!multiRegion) {
    for (const auto& layer : layers_) {
      if (layer->applies(ctx)) {
        layer->draw(ctx, theme_);
      }
    }
    return;
  }

  // Multi-region path: region-scope layers run once per region with the
  // scoped context; widget-scope layers run once at the end with the
  // whole-widget context. Mirrors Python `Painter.paint` + iter_regions.
  // Regions are sorted by (z_index, position) — lowest first for paint order.
  std::vector<std::size_t> paintOrder(controller->regions().size());
  for (std::size_t i = 0; i < paintOrder.size(); ++i) {
    paintOrder[i] = i;
  }
  std::stable_sort(paintOrder.begin(), paintOrder.end(),
                   [&](std::size_t a, std::size_t b) {
                     const auto& ra = controller->regions()[a];
                     const auto& rb = controller->regions()[b];
                     if (ra.zIndex != rb.zIndex) return ra.zIndex < rb.zIndex;
                     return a < b;
                   });
  for (auto idx : paintOrder) {
    const auto& region = controller->regions()[idx];
    DrawContext::ScopeArgs args;
    args.regionId = region.id;
    args.rect = controller->rectFor(region.id);
    args.path = controller->pathFor(region.id);
    args.states = controller->states(region.id);
    if (region.variant.has_value()) {
      args.variant = getVariant(*region.variant);
    }
    args.overrideBgColor = region.overrideBgColor;
    args.customBgColor = region.customBgColor;
    args.overrideBorderColor = region.overrideBorderColor;
    args.showUnderline = region.showUnderline;
    args.underlineColor = region.underlineColor;
    args.underlineThickness = region.underlineThickness;
    args.iconSizePx = region.iconSizePx;
    // Region-local content selection mirrors Python `_build_region_content`:
    // rows → RowsContent, icon+text → IconTextContent, text → TextContent,
    // icon → IconContent. Falls back to widget-scope content when the region
    // carries no payload of its own.
    auto regionContent = buildContentFromRegion(region);
    args.content = regionContent ? regionContent : ctx.content;
    const DrawContext scoped = ctx.scopedTo(args);
    for (const auto& layer : layers_) {
      if (layer->scope() != LayerScope::Region) {
        continue;
      }
      if (layer->applies(scoped)) {
        layer->draw(scoped, theme_);
      }
    }
  }

  for (const auto& layer : layers_) {
    if (layer->scope() != LayerScope::Widget) {
      continue;
    }
    if (layer->applies(ctx)) {
      layer->draw(ctx, theme_);
    }
  }
}

}  // namespace sli::toolkit::buttons
