#include "sli/toolkit/buttons/button_group.h"

#include <QFont>
#include <QFontMetrics>
#include <QHBoxLayout>
#include <QPainter>
#include <QPen>
#include <QRect>
#include <Qt>

#include <algorithm>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

ButtonGroup::ButtonGroup(std::vector<QWidget*> buttons, const QString& label,
                         QWidget* parent)
    : QWidget(parent), label_(label) {
  setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
  setAutoFillBackground(false);
  setAttribute(Qt::WA_StyledBackground, false);
  layout_ = new QHBoxLayout(this);
  layout_->setContentsMargins(10, 8, 10, 18);
  layout_->setSpacing(2);
  for (QWidget* button : buttons) {
    layout_->addWidget(button);
  }
  // Python: `self.theme_manager.theme_changed.connect(self.update)`
  Theme::onThemeChanged(this, [this] { update(); });
}

void ButtonGroup::setLabel(const QString& text) {
  if (label_ != text) {
    label_ = text;
    update();
  }
}

void ButtonGroup::addButton(QWidget* button) {
  if (button != nullptr && layout_ != nullptr) {
    layout_->addWidget(button);
  }
}

void ButtonGroup::paintEvent(QPaintEvent*) {
  // Port of Python `ButtonGroup.paintEvent` — label centred *below* the
  // border with a small bg-coloured gap punched in the bottom border line so
  // the text reads as a legend over the group rectangle.
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);

  const QColor borderColor = Theme::getColor(QStringLiteral("dialog.border"));
  const QColor bgColor = Theme::getColor(QStringLiteral("Window"));
  const QColor textColor = Theme::getColor(QStringLiteral("WindowText"));

  const QRect r = this->rect();
  QFont font = painter.font();
  font.setPointSize(std::max(8, font.pointSize() - 2));
  painter.setFont(font);
  const QFontMetrics fm(font);
  const int labelHeight = label_.isEmpty() ? 0 : fm.height();

  painter.setPen(QPen(borderColor, borderWidth_));
  painter.setBrush(Qt::NoBrush);
  painter.translate(0.5, 0.5);

  constexpr int marginV = 3;
  constexpr int marginH = 6;
  const int bottomY = r.height() - labelHeight / 2;
  const QRect drawRect(marginH, marginV, r.width() - marginH * 2 - 1,
                       bottomY - marginV * 2);
  painter.drawRoundedRect(drawRect, borderRadius_, borderRadius_);
  painter.translate(-0.5, -0.5);

  if (!label_.isEmpty()) {
    constexpr int labelPadding = 3;
    const int centerX = r.width() / 2;
    const int labelW = fm.horizontalAdvance(label_);
    const int labelH = fm.height();

    const int actualBottomY = bottomY - marginV;
    const int gapY = actualBottomY - borderWidth_;
    const int gapHeight = borderWidth_ * 2 + 1;

    painter.setPen(Qt::NoPen);
    const QRect gapRect(centerX - labelW / 2 - labelPadding, gapY,
                        labelW + labelPadding * 2, gapHeight);
    painter.fillRect(gapRect, bgColor);

    const QRect textRect(centerX - labelW / 2, r.height() - labelH - 2,
                         labelW, labelH);
    painter.setPen(textColor);
    painter.drawText(textRect, Qt::AlignCenter, label_);
  }
}

}  // namespace sli::toolkit
