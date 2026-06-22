#include "sli/toolkit/buttons/content/content.h"

#include <QFont>
#include <QFontMetrics>
#include <QIcon>
#include <QPainter>
#include <QPixmap>
#include <QRect>
#include <QRectF>
#include <Qt>

#include <algorithm>

#include "sli/toolkit/buttons/draw_context.h"
#include "sli/toolkit/buttons/regions.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

namespace {

QRect alignedRect(const DrawContext& ctx) {
  return ctx.effectiveRect().toAlignedRect();
}

QColor textColor(const DrawContext& ctx, const Theme& theme) {
  // Python's `_text_color`: style.foreground_color or tm.get_color("dialog.text").
  // No per-state alpha override — the theme token carries the right color.
  (void)ctx;
  return theme.getColor(QStringLiteral("dialog.text"));
}

}  // namespace

void TextContent::draw(const DrawContext& ctx, const Theme& theme) const {
  QPainter* p = ctx.painter;
  p->setPen(textColor(ctx, theme));
  const QRect rect = alignedRect(ctx);
  if (text_.contains(QLatin1Char('\n'))) {
    const auto lines = text_.split(QLatin1Char('\n'));
    QFontMetrics fm = p->fontMetrics();
    const int lineH = fm.lineSpacing();
    const int totalH = lineH * lines.size();
    int startY = rect.y() + (rect.height() - totalH) / 2;
    for (const auto& line : lines) {
      p->drawText(QRect(rect.x(), startY, rect.width(), lineH),
                  Qt::AlignCenter, line);
      startY += lineH;
    }
  } else {
    p->drawText(rect, Qt::AlignCenter, text_);
  }
}

void RowsContent::draw(const DrawContext& ctx, const Theme& theme) const {
  if (rows_.empty()) {
    return;
  }
  QPainter* p = ctx.painter;
  const QRect rect = alignedRect(ctx);
  const int widgetH = rect.height();
  const int widgetW = rect.width();
  const QColor defaultColor = textColor(ctx, theme);

  auto drawRow = [&](const ButtonRow& row, int x, int y, int width, int height) {
    QFont f;
    f.setPixelSize(row.size);
    if (row.weight == RowWeight::Bold) {
      f.setBold(true);
    }
    p->setFont(f);
    p->setPen(row.color.value_or(defaultColor));
    p->drawText(QRect(x, y, width, height),
                row.hAlign | Qt::AlignVCenter, row.text);
  };

  if (compact_) {
    std::vector<int> heights;
    heights.reserve(rows_.size());
    for (const auto& row : rows_) {
      QFont f;
      f.setPixelSize(row.size);
      if (row.weight == RowWeight::Bold) {
        f.setBold(true);
      }
      heights.push_back(QFontMetrics(f).lineSpacing());
    }
    int total = 0;
    for (int h : heights) {
      total += h;
    }
    total += rowGap_ * static_cast<int>(std::max<std::size_t>(0, rows_.size() - 1));
    int y = rect.y() + std::max(0, (widgetH - total) / 2);
    for (std::size_t i = 0; i < rows_.size(); ++i) {
      drawRow(rows_[i], rect.x(), y, widgetW, heights[i]);
      y += heights[i] + rowGap_;
    }
  } else {
    int y = rect.y();
    for (const auto& row : rows_) {
      const int rh = static_cast<int>(widgetH * row.ratio);
      if (rh <= 0) {
        continue;
      }
      drawRow(row, rect.x(), y, widgetW, rh);
      y += rh;
    }
  }
}

void IconContent::draw(const DrawContext& ctx, const Theme& theme) const {
  QPainter* p = ctx.painter;
  const QRect rect = alignedRect(ctx);
  const bool isChecked = ctx.effectiveStates().testFlag(ButtonState::Checked);
  const QIcon& current = (isChecked && !iconChecked_.isNull()) ? iconChecked_
                                                                : iconUnchecked_;
  if (current.isNull()) {
    return;
  }
  const int iconSize = ctx.effectiveIconSizePx();
  const auto scrollValue = ctx.scrollValue;
  const bool alwaysVisible = ctx.scrollValueAlwaysVisible;
  const bool isToggleScroll = scrollValue.has_value() && !alwaysVisible;
  const bool isHovered = ctx.effectiveStates().testFlag(ButtonState::Hovered);
  const bool isScrolling = ctx.effectiveStates().testFlag(ButtonState::Scrolling);

  if (isToggleScroll && isHovered && !isScrolling) {
    drawWithHoverValue(p, rect, current, *scrollValue, iconSize);
  } else {
    drawStandard(p, rect, current, scrollValue, alwaysVisible,
                 isToggleScroll, iconSize);
  }
}

void IconContent::drawStandard(QPainter* p, const QRect& rect,
                                const QIcon& icon,
                                std::optional<int> scrollValue,
                                bool alwaysVisible, bool isToggleScroll,
                                int iconSize) {
  const bool showValueChip =
      scrollValue.has_value() && alwaysVisible && *scrollValue != 0;
  const int actual =
      showValueChip ? std::max(12, iconSize - 4) : iconSize;
  const QPixmap pixmap = icon.pixmap(actual, actual);

  const double opacity =
      (isToggleScroll && scrollValue.has_value() && *scrollValue == 0) ? 0.4
                                                                       : 1.0;
  p->save();
  p->setOpacity(opacity);
  const int x = rect.x() + (rect.width() - actual) / 2;
  int y;
  if (showValueChip) {
    constexpr int valueH = 12;
    constexpr int gap = 2;
    y = rect.y() + std::max(1, (rect.height() - actual - valueH - gap) / 2);
  } else {
    y = rect.y() + (rect.height() - actual) / 2;
  }
  p->drawPixmap(x, y, pixmap);
  p->restore();

  if (showValueChip) {
    drawScrollValueBelow(p, rect, *scrollValue);
  }
}

void IconContent::drawWithHoverValue(QPainter* p, const QRect& rect,
                                      const QIcon& icon, int scrollValue,
                                      int iconSize) {
  const int hoverSize = std::max(14, iconSize - 3);
  const QPixmap pixmap = icon.pixmap(hoverSize, hoverSize);
  const int h = rect.height();
  constexpr int valueH = 10;
  constexpr int gap = 2;
  const int iconY =
      rect.y() + std::max(1, (h - hoverSize - valueH - gap) / 2);
  const int valueY = iconY + hoverSize + gap;

  const double opacity = (scrollValue == 0) ? 0.4 : 1.0;
  p->save();
  p->setOpacity(opacity);
  p->drawPixmap(rect.x() + (rect.width() - hoverSize) / 2, iconY, pixmap);
  p->restore();

  drawValueText(p, rect, valueY, valueH,
                scrollValue == 0 ? QStringLiteral("0")
                                 : QString::number(scrollValue));
}

void IconContent::drawScrollValueBelow(QPainter* p, const QRect& rect,
                                        int value) {
  constexpr int valueH = 12;
  const int valueY = rect.y() + rect.height() - valueH - 1;
  drawValueText(p, rect, valueY, valueH, QString::number(value));
}

void IconContent::drawValueText(QPainter* p, const QRect& rect, int y,
                                 int height, const QString& text) {
  QFont f;
  f.setPixelSize(9);
  f.setBold(true);
  p->save();
  p->setFont(f);
  // Python's `_draw_value_text` uses style.foreground_color or dialog.text.
  p->setPen(Theme::palette().text);
  p->drawText(QRect(rect.x(), y, rect.width(), height), Qt::AlignCenter, text);
  p->restore();
}

void IconTextContent::draw(const DrawContext& ctx, const Theme& theme) const {
  QPainter* p = ctx.painter;
  const QRect rect = alignedRect(ctx);
  const int iconPx = ctx.effectiveIconSizePx();
  const QPixmap pixmap = icon_.pixmap(iconPx, iconPx);

  QFontMetrics fm = p->fontMetrics();
  const int totalW = iconPx + 6 + fm.horizontalAdvance(text_);
  const int startX = rect.x() + (rect.width() - totalW) / 2;
  const int iconY = rect.y() + (rect.height() - iconPx) / 2;

  p->drawPixmap(startX, iconY, pixmap);
  p->setPen(textColor(ctx, theme));
  p->drawText(QRect(startX + iconPx + 6, rect.y(), rect.width(), rect.height()),
              Qt::AlignVCenter, text_);
}

std::shared_ptr<Content> buildContentFromRegion(const ButtonRegion& region) {
  if (region.rows.has_value() && !region.rows->empty()) {
    return std::make_shared<RowsContent>(*region.rows);
  }
  QIcon icon;
  if (region.icon.isValid() && region.icon.canConvert<QIcon>()) {
    icon = region.icon.value<QIcon>();
  }
  // Mirror Python `icon=(unchecked, checked)` — alternate icon shown when
  // ButtonState::Checked is on. Falls back to the primary icon for both
  // states when no alternate is provided.
  QIcon iconChecked = icon;
  if (region.iconChecked.isValid() &&
      region.iconChecked.canConvert<QIcon>()) {
    QIcon alt = region.iconChecked.value<QIcon>();
    if (!alt.isNull()) {
      iconChecked = alt;
    }
  }
  const bool hasIcon = !icon.isNull();
  const bool hasText = !region.text.isEmpty();
  if (hasIcon && hasText) {
    return std::make_shared<IconTextContent>(icon, region.text);
  }
  if (hasText) {
    return std::make_shared<TextContent>(region.text);
  }
  if (hasIcon) {
    return std::make_shared<IconContent>(icon, iconChecked);
  }
  return nullptr;
}

}  // namespace sli::toolkit::buttons
