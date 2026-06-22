#include "sli/toolkit/buttons/layers/content_layer.h"

#include <QPainter>

#include "sli/toolkit/buttons/content/content.h"
#include "sli/toolkit/buttons/draw_context.h"

namespace sli::toolkit::buttons {

bool ContentLayer::applies(const DrawContext& ctx) const {
  return static_cast<bool>(ctx.effectiveContent());
}

void ContentLayer::draw(const DrawContext& ctx, const Theme& theme) const {
  auto content = ctx.effectiveContent();
  if (!content) {
    return;
  }
  if (!ctx.regionPath.has_value()) {
    content->draw(ctx, theme);
    return;
  }
  QPainter* p = ctx.painter;
  p->save();
  p->setClipPath(ctx.effectivePath());
  content->draw(ctx, theme);
  p->restore();
}

}  // namespace sli::toolkit::buttons
