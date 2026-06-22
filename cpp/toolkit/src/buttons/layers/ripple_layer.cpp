#include "sli/toolkit/buttons/layers/ripple_layer.h"

#include <QBrush>
#include <QColor>
#include <QPainter>
#include <QPainterPath>
#include <Qt>

#include <algorithm>
#include <cmath>

#include "sli/toolkit/buttons/controller.h"
#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

namespace {

RippleEffect* rippleFor(const DrawContext& ctx) {
  if (ctx.widget == nullptr) {
    return nullptr;
  }
  auto* controller =
      ctx.widget->property("buttonController").value<ButtonController*>();
  if (controller == nullptr) {
    return nullptr;
  }
  // Region-scope: use the scoped regionId.  Widget-scope (single-region
  // paint or regionId not yet set): fall back to "_main" so ripples fire
  // for buttons that don't go through the multi-region path.
  QString id = ctx.regionId.value_or(QStringLiteral("_main"));
  return controller->ripple(id);
}

}  // namespace

bool RippleLayer::applies(const DrawContext& ctx) const {
  RippleEffect* ripple = rippleFor(ctx);
  return ripple != nullptr && ripple->isActive();
}

void RippleLayer::draw(const DrawContext& ctx, const Theme& theme) const {
  RippleEffect* ripple = rippleFor(ctx);
  if (ripple == nullptr || !ripple->isActive()) {
    return;
  }
  auto center = ripple->center();
  if (!center.has_value()) {
    return;
  }

  const double progress = ripple->progress();
  const double eased = 1.0 - std::pow(1.0 - progress, 2.0);

  const QRectF rect = ctx.effectiveRect();
  const std::array<QPointF, 4> corners{
      QPointF(rect.left(), rect.top()), QPointF(rect.right(), rect.top()),
      QPointF(rect.left(), rect.bottom()), QPointF(rect.right(), rect.bottom())};
  double maxRadius = 0.0;
  for (const auto& c : corners) {
    const double dx = center->x() - c.x();
    const double dy = center->y() - c.y();
    maxRadius = std::max(maxRadius, std::hypot(dx, dy));
  }
  const double radius = maxRadius * eased;
  if (radius <= 0.0) {
    return;
  }

  QPainter* p = ctx.painter;
  p->save();
  QPainterPath clip;
  const int radiusCorner = std::max(0, ctx.cornerRadius - 1);
  clip.addRoundedRect(ctx.rect.adjusted(1.0, 1.0, -1.0, -1.0), radiusCorner,
                      radiusCorner);
  p->setClipPath(clip);
  if (ctx.regionRect.has_value()) {
    p->setClipPath(ctx.effectivePath(), Qt::IntersectClip);
  }
  p->setRenderHint(QPainter::Antialiasing);
  p->setPen(Qt::NoPen);

  if (ripple->colorFrom().has_value() && ripple->colorTo().has_value()) {
    p->setBrush(QBrush(*ripple->colorFrom()));
    p->drawRect(rect);
    p->setBrush(QBrush(*ripple->colorTo()));
    p->drawEllipse(*center, radius, radius);
  } else {
    const bool dark = theme.isDark();
    const int peak = dark ? RippleEffect::kPeakAlphaDark
                          : RippleEffect::kPeakAlphaLight;
    const int alpha = static_cast<int>(peak * (1.0 - progress));
    if (alpha > 0) {
      QColor color =
          dark ? QColor(255, 255, 255, alpha) : QColor(0, 0, 0, alpha);
      p->setBrush(color);
      p->drawEllipse(*center, radius, radius);
    }
  }
  p->restore();
}

}  // namespace sli::toolkit::buttons
