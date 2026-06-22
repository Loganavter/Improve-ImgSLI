#include "sli/toolkit/buttons/layers/divider_layer.h"

#include <QLineF>
#include <QPainter>
#include <QPen>

#include <cmath>

#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

namespace {

QLineF insetLine(const QLineF& line, double margin) {
  if (std::abs(line.x1() - line.x2()) < 0.01) {
    return QLineF(line.x1(), line.y1() + margin, line.x2(), line.y2() - margin);
  }
  return QLineF(line.x1() + margin, line.y1(), line.x2() - margin, line.y2());
}

}  // namespace

bool DividerLayer::applies(const DrawContext& ctx) const {
  // Controller-aware applies requires controller access on the widget — the
  // Painter shell binds this through ctx.widget property lookup in D5; until
  // then we rely on the widget exposing a `dividerEnabled` dynamic property.
  return ctx.widget != nullptr &&
         ctx.widget->property("dividerEnabled").toBool();
}

void DividerLayer::draw(const DrawContext& ctx, const Theme& theme) const {
  if (ctx.widget == nullptr) {
    return;
  }
  // Divider geometry is set by the widget through `dividerLines` (a
  // QList<QLineF>) and `dividerColor`/`dividerThickness`/`dividerMargin`
  // dynamic properties. D5 will replace this with controller access.
  const QVariant linesVar = ctx.widget->property("dividerLines");
  if (!linesVar.isValid()) {
    return;
  }
  const auto lines = linesVar.value<QList<QLineF>>();
  if (lines.isEmpty()) {
    return;
  }
  QColor color = ctx.widget->property("dividerColor").value<QColor>();
  if (!color.isValid()) {
    color = theme.palette().border;
  }
  const double thickness =
      ctx.widget->property("dividerThickness").toDouble();
  const double margin = ctx.widget->property("dividerMargin").toDouble();
  QPainter* p = ctx.painter;
  p->save();
  p->setPen(QPen(color, thickness > 0 ? thickness : 1.0));
  for (const auto& line : lines) {
    p->drawLine(insetLine(line, margin));
  }
  p->restore();
}

}  // namespace sli::toolkit::buttons
