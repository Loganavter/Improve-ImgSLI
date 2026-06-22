#include "sli/toolkit/atomic/radio_button.h"

#include <QPainter>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

RadioButton::RadioButton(const QString& text, QWidget* parent)
    : QAbstractButton(parent) {
    setText(text);
    setCheckable(true);
    setAutoExclusive(true);
    setCursor(Qt::PointingHandCursor);
    setFocusPolicy(Qt::StrongFocus);
    setMinimumHeight(24);
}

QSize RadioButton::sizeHint() const {
    const int textWidth = text().isEmpty()
        ? 0
        : fontMetrics().horizontalAdvance(text()) + kSpacing;
    const int height = qMax(kDiameter + 4, fontMetrics().height() + 4);
    return {kDiameter + textWidth + 4, height};
}

void RadioButton::paintEvent(QPaintEvent*) {
    const auto& colors = Theme::palette();

    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    const int boxY = (height() - kDiameter) / 2;
    const QRect outer(2, boxY, kDiameter, kDiameter);

    QColor border = hasFocus() ? colors.accent : colors.border;
    QColor fill = colors.base;
    if (underMouse() && !isChecked()) {
        fill = colors.hover;
    }

    p.setPen(QPen(border, hasFocus() ? 1.5 : 1.0));
    p.setBrush(fill);
    p.drawEllipse(outer);

    if (isChecked()) {
        const int inset = 4;
        const QRect inner = outer.adjusted(inset, inset, -inset, -inset);
        p.setPen(Qt::NoPen);
        p.setBrush(colors.accent);
        p.drawEllipse(inner);
    }

    if (!text().isEmpty()) {
        const QRect textRect(outer.right() + kSpacing, 0,
                             width() - outer.right() - kSpacing, height());
        QColor textColor = colors.windowText;
        if (!isEnabled()) {
            textColor.setAlpha(110);
        }
        p.setPen(textColor);
        p.drawText(textRect, Qt::AlignLeft | Qt::AlignVCenter, text());
    }
}

}  // namespace sli::toolkit
