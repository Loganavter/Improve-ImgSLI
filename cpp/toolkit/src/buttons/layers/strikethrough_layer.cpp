#include "sli/toolkit/buttons/layers/strikethrough_layer.h"

#include <QColor>
#include <QPainter>
#include <QPen>
#include <QWidget>

#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

bool StrikethroughLayer::applies(const DrawContext& ctx) const {
  return ctx.showStrikeThrough;
}

void StrikethroughLayer::draw(const DrawContext& ctx, const Theme& theme) const {
  if (ctx.widget == nullptr) {
    return;
  }
  QColor color = theme.isDark() ? QColor(QStringLiteral("#ff4444"))
                                 : QColor(QStringLiteral("#cc0000"));
  color.setAlpha(180);
  ctx.painter->setPen(QPen(color, 2));
  ctx.painter->drawLine(4, ctx.widget->height() - 4, ctx.widget->width() - 4,
                        4);
}

}  // namespace sli::toolkit::buttons
