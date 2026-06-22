#include "sli/toolkit/buttons/layers/badge_layer.h"

#include <QFont>
#include <QPainter>
#include <QRect>
#include <QWidget>

#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

bool BadgeLayer::applies(const DrawContext& ctx) const {
  return ctx.badgeText.has_value();
}

void BadgeLayer::draw(const DrawContext& ctx, const Theme& theme) const {
  if (!ctx.badgeText.has_value() || ctx.widget == nullptr) {
    return;
  }
  QPainter* p = ctx.painter;
  QFont f;
  f.setBold(true);
  f.setPixelSize(9);
  p->setFont(f);

  QColor textColor = theme.palette().text;
  if (ctx.states.testFlag(ButtonState::Checked)) {
    textColor.setAlpha(140);
  } else if (ctx.states.testFlag(ButtonState::Disabled)) {
    textColor.setAlpha(120);
  }
  p->setPen(textColor);
  const QRect r(ctx.widget->width() - 14, 1, 12, 10);
  p->drawText(r, Qt::AlignCenter, *ctx.badgeText);
}

}  // namespace sli::toolkit::buttons
