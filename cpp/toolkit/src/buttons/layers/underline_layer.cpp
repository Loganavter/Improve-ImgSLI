#include "sli/toolkit/buttons/layers/underline_layer.h"

#include <QColor>
#include <QPainter>
#include <QPen>
#include <QPointF>
#include <QRectF>

#include <algorithm>
#include <cmath>

#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

namespace {

constexpr double kMaxUnderlineThickness = 3.0;
constexpr int kTaperSegments = 24;

double widgetScale(const QRectF& rect) {
  return std::max(1.0, rect.height() / 32.0);
}

// Draw a tapered arc with varying alpha along the sweep.
// Mirrors Python `_draw_tapered_arc`.
void drawTaperedArc(QPainter* painter,
                    const QColor& baseColor,
                    double thickness,
                    double cx, double cy,
                    double radius,
                    double startDeg, double sweepDeg,
                    int fullAlpha,
                    double alphaAtStart,
                    double alphaAtEnd) {
  QPen pen(baseColor);
  pen.setWidthF(thickness);
  pen.setCapStyle(Qt::FlatCap);

  QPointF prevPt;
  for (int s = 0; s <= kTaperSegments; ++s) {
    const double t = static_cast<double>(s) / kTaperSegments;
    const double ang = (startDeg + sweepDeg * t) * M_PI / 180.0;
    const double x = cx + radius * std::cos(ang);
    const double y = cy - radius * std::sin(ang);
    const QPointF pt(x, y);

    if (s > 0) {
      const double tMid = (s - 0.5) / kTaperSegments;
      const double alphaNorm =
          alphaAtStart + (alphaAtEnd - alphaAtStart) * tMid;
      const int alphaVal =
          static_cast<int>(std::round(fullAlpha *
                                      std::max(0.0, std::min(1.0, alphaNorm))));
      QColor segColor(baseColor);
      segColor.setAlpha(alphaVal);
      pen.setColor(segColor);
      painter->setPen(pen);
      painter->drawLine(prevPt, pt);
    }
    prevPt = pt;
  }
}

}  // namespace

bool UnderlineLayer::applies(const DrawContext& ctx) const {
  return ctx.effectiveShowUnderline() || ctx.scrollValue.has_value();
}

void UnderlineLayer::draw(const DrawContext& ctx, const Theme& theme) const {
  QPainter* p = ctx.painter;

  // --- resolve color ---
  // Python: resolved = ctx.effective_underline_color or style.underline_color;
  // fallback to accent with alpha tweaks.
  QColor color;
  QVariant explicitColor = ctx.effectiveUnderlineColor();
  if (explicitColor.isValid() && explicitColor.canConvert<QColor>()) {
    color = explicitColor.value<QColor>();
  } else if (ctx.effectiveShowUnderline() || ctx.scrollValue.has_value()) {
    color = Theme::getColor(QStringLiteral("accent"));
  } else {
    return;
  }

  int alpha = color.alpha();
  const bool hasExplicit =
      explicitColor.isValid() && explicitColor.canConvert<QColor>();
  if (hasExplicit) {
    alpha = std::min(alpha, 100);
  } else {
    alpha = (alpha < 255) ? alpha
           : (ctx.scrollValue.has_value() ? 40 : 200);
  }
  color.setAlpha(alpha);

  // --- thickness ---
  double thickness =
      ctx.effectiveUnderlineThickness().value_or(
          ctx.scrollValue.has_value() ? 2.0 : 1.0);
  thickness = std::max(0.0, std::min(thickness, kMaxUnderlineThickness));

  // --- geometry ---
  const QRectF rect = ctx.effectiveRect();
  const double scale = widgetScale(rect);
  const double arcRadius = std::max(0, ctx.cornerRadius) / scale;
  const double verticalOffset = 0.0;
  const double baseY = rect.bottom() - verticalOffset;
  const double startX = rect.left();
  const double endX = rect.right();

  const int fullAlpha = color.alpha();

  // Line segment between arcs.
  const double lineStartX = startX + arcRadius;
  const double lineEndX = endX - arcRadius;
  if (lineEndX > lineStartX) {
    QPen linePen(color);
    linePen.setWidthF(thickness);
    linePen.setCapStyle(Qt::FlatCap);
    p->save();
    p->setPen(linePen);
    p->drawLine(QPointF(lineStartX, baseY), QPointF(lineEndX, baseY));
    p->restore();
  }

  // Left arc — 180°→270°, alpha ramps 0→full.
  if (arcRadius > 0) {
    const double cx = startX + arcRadius;
    const double cy = baseY - arcRadius;
    drawTaperedArc(p, color, thickness, cx, cy, arcRadius,
                   180.0, 90.0, fullAlpha, 0.0, 1.0);

    // Right arc — 270°→360°, alpha ramps full→0.
    const double cx2 = endX - arcRadius;
    const double cy2 = baseY - arcRadius;
    drawTaperedArc(p, color, thickness, cx2, cy2, arcRadius,
                   270.0, 90.0, fullAlpha, 1.0, 0.0);
  }
}

}  // namespace sli::toolkit::buttons