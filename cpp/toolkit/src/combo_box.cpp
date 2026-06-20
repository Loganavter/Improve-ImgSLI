#include "sli/toolkit/combo_box.h"

#include <QPainter>
#include <QPainterPath>
#include <QStyleOptionComboBox>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

ComboBox::ComboBox(QWidget* parent)
    : QComboBox(parent) {
    setFocusPolicy(Qt::StrongFocus);
    setMinimumHeight(33);
}

QSize ComboBox::sizeHint() const {
    const QSize base = QComboBox::sizeHint();
    return {qMax(100, base.width()), 33};
}

void ComboBox::paintEvent(QPaintEvent*) {
    const auto& colors = Theme::palette();
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setPen(QPen(hasFocus() ? colors.accent : colors.border, hasFocus() ? 1.5 : 1.0));
    painter.setBrush(underMouse() ? colors.hover : colors.base);
    painter.drawRoundedRect(rect().adjusted(1, 1, -1, -1), 8, 8);

    const QRect textRect = rect().adjusted(10, 0, -28, 0);
    painter.setPen(colors.text);
    painter.drawText(textRect, Qt::AlignVCenter | Qt::AlignLeft, currentText());

    const QPointF center(width() - 14.0, height() / 2.0);
    QPainterPath arrow;
    arrow.moveTo(center.x() - 4, center.y() - 2);
    arrow.lineTo(center.x(), center.y() + 2);
    arrow.lineTo(center.x() + 4, center.y() - 2);
    painter.setPen(QPen(colors.text, 1.5));
    painter.setBrush(Qt::NoBrush);
    painter.drawPath(arrow);
}

}  // namespace sli::toolkit
