#include "sli/toolkit/buttons/layers/background_layer.h"

#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QRectF>
#include <Qt>

#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/buttons/variants.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

namespace {

QPainterPath footerPath(const QRectF& rect, int radius) {
  QPainterPath path;
  path.moveTo(rect.left(), rect.top());
  path.lineTo(rect.right(), rect.top());
  path.arcTo(rect.right() - 2 * radius, rect.bottom() - 2 * radius, 2 * radius,
             2 * radius, 0, -90);
  path.arcTo(rect.left(), rect.bottom() - 2 * radius, 2 * radius, 2 * radius,
             270, -90);
  path.closeSubpath();
  return path;
}

struct Resolved {
  QColor background;
  std::optional<QColor> border;
};

// Python `BackgroundLayer._resolve` cascade:
//   override → custom-tint → variant token.
Resolved resolveColors(const DrawContext& ctx, const Theme& theme) {
  StateSet states = ctx.effectiveStates();
  const VariantSpec& variant = ctx.effectiveVariant();

  if (auto override = ctx.effectiveOverrideBg(); override.has_value()) {
    return {*override, std::nullopt};
  }

  if (auto custom = ctx.effectiveCustomBg(); custom.has_value()) {
    CustomPalette pal = deriveCustomPalette(*custom, variant.name);
    QColor bg;
    if (states.testFlag(ButtonState::Disabled)) {
      bg = pal.disabled;
    } else if (states.testFlag(ButtonState::Pressed)) {
      bg = pal.pressed;
    } else if (states.testFlag(ButtonState::Hovered)) {
      bg = pal.hover;
    } else {
      bg = pal.normal;
    }
    const bool enabled = ctx.widget == nullptr || ctx.widget->isEnabled();
    return {bg, enabled ? pal.border : std::nullopt};
  }

  const QColor bg = resolveBackground(variant, states, theme);
  std::optional<QColor> border;
  if (ctx.widget != nullptr && ctx.widget->isEnabled()) {
    if (auto themed =
            theme.tryGetColor(variant.tokenPrefix + QStringLiteral(".border"));
        themed.has_value()) {
      border = *themed;
    }
  }
  return {bg, border};
}

}  // namespace

void BackgroundLayer::draw(const DrawContext& ctx, const Theme& theme) const {
  QPainter* p = ctx.painter;
  p->setRenderHint(QPainter::Antialiasing);

  Resolved resolved = resolveColors(ctx, theme);
  QColor bg = resolved.background;
  std::optional<QColor> borderColor = resolved.border;
  if (auto overrideBorder = ctx.effectiveOverrideBorder();
      overrideBorder.has_value()) {
    borderColor = *overrideBorder;
  }

  const int radius = std::max(0, ctx.cornerRadius);
  const QRectF widgetRect = ctx.rect.adjusted(0.5, 0.5, -0.5, -0.5);
  std::optional<QPainterPath> path;
  if (ctx.isFooter) {
    path = footerPath(widgetRect, radius);
  }

  const QRectF regionRect = ctx.effectiveRect();
  const bool isSubregion = ctx.regionId.has_value() && regionRect != ctx.rect;

  p->setPen(Qt::NoPen);
  p->setBrush(bg);

  if (isSubregion) {
    QPainterPath outer;
    if (path.has_value()) {
      outer = *path;
    } else {
      outer.addRoundedRect(widgetRect, radius, radius);
    }
    QPainterPath regionPath = ctx.effectivePath();
    p->save();
    p->setClipPath(outer);
    p->setClipPath(regionPath, Qt::IntersectClip);
    p->drawPath(regionPath);
    p->restore();
  } else if (path.has_value()) {
    p->drawPath(*path);
  } else {
    p->drawRoundedRect(widgetRect, radius, radius);
  }

  if (borderColor.has_value() && !isSubregion) {
    p->setPen(QPen(*borderColor, 1.0));
    p->setBrush(Qt::NoBrush);
    if (path.has_value()) {
      p->drawPath(*path);
    } else {
      p->drawRoundedRect(widgetRect, radius, radius);
    }
  }
}

}  // namespace sli::toolkit::buttons
