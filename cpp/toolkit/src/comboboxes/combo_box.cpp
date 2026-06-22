#include "sli/toolkit/comboboxes/combo_box.h"

#include <QPainter>
#include <QPainterPath>
#include <QStyleOptionComboBox>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

namespace {
constexpr int kRadius = 6;
constexpr int kTextHPad = 12;
constexpr int kArrowRightMargin = 14;
constexpr int kBaseHeight = 33;
}  // namespace

ComboBox::ComboBox(QWidget* parent)
    : QComboBox(parent) {
    setFocusPolicy(Qt::StrongFocus);
    setMinimumHeight(kBaseHeight);
}

QSize ComboBox::sizeHint() const {
    const QSize base = QComboBox::sizeHint();
    return {qMax(100, base.width()), kBaseHeight};
}

void ComboBox::paintEvent(QPaintEvent*) {
    const Palette& colors = Theme::palette();
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    // Background fill — mirror Python's _ComboFieldBgLayer token choices.
    const QColor inputBg = Theme::getColor(QStringLiteral("dialog.input.background"));
    const QColor hoverBg = Theme::getColor(QStringLiteral("list_item.background.hover"));
    painter.setPen(Qt::NoPen);
    painter.setBrush(underMouse() ? hoverBg : inputBg);
    painter.drawRoundedRect(rect().adjusted(1, 1, -1, -1), kRadius, kRadius);

    // Border — mirror Python's input.border.thin, 1.0 width.
    const QColor borderColor = Theme::getColor(QStringLiteral("input.border.thin"));
    painter.setPen(QPen(borderColor, 1.0));
    painter.setBrush(Qt::NoBrush);
    painter.drawRoundedRect(QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5), kRadius, kRadius);

    // Text.
    const QRect textRect = rect().adjusted(kTextHPad, 0, -(kArrowRightMargin + 14), 0);
    painter.setPen(colors.text);
    painter.drawText(textRect, Qt::AlignVCenter | Qt::AlignLeft, currentText());

    // Arrow — polyline matching Python coordinates: (cx-4, cy-1), (cx, cy+2), (cx+4, cy-1).
    const QPointF center(width() - kArrowRightMargin, height() / 2.0);
    const QPointF poly[3] = {
        QPointF(center.x() - 4, center.y() - 1),
        QPointF(center.x(),     center.y() + 2),
        QPointF(center.x() + 4, center.y() - 1),
    };
    painter.setPen(QPen(colors.text, 1.5));
    painter.setBrush(Qt::NoBrush);
    painter.drawPolyline(poly, 3);
}

}  // namespace sli::toolkit
