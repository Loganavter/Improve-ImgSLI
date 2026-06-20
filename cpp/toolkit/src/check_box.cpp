#include "sli/toolkit/check_box.h"

#include <QPainter>
#include <QPainterPath>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

CheckBox::CheckBox(const QString& text, QWidget* parent)
    : QAbstractButton(parent) {
    setText(text);
    setCheckable(true);
    setCursor(Qt::PointingHandCursor);
    setFocusPolicy(Qt::StrongFocus);
    setMinimumHeight(24);
}

QSize CheckBox::sizeHint() const {
    const int textWidth = text().isEmpty()
        ? 0
        : fontMetrics().horizontalAdvance(text()) + kSpacing;
    const int height = qMax(kBoxSize + 4, fontMetrics().height() + 4);
    return {kBoxSize + textWidth + 4, height};
}

void CheckBox::paintEvent(QPaintEvent*) {
    const auto& colors = Theme::palette();

    QPainter p(this);
    p.setRenderHint(QPainter::Antialiasing);

    const int boxY = (height() - kBoxSize) / 2;
    const QRect box(2, boxY, kBoxSize, kBoxSize);

    QColor border = hasFocus() ? colors.accent : colors.border;
    QColor fill = isChecked() ? colors.accent : colors.base;
    if (underMouse() && !isChecked()) {
        fill = colors.hover;
    }

    p.setPen(QPen(border, hasFocus() ? 1.5 : 1.0));
    p.setBrush(fill);
    p.drawRoundedRect(box, 3, 3);

    if (isChecked()) {
        QPen checkPen(colors.buttonText, 2.0);
        checkPen.setCapStyle(Qt::RoundCap);
        checkPen.setJoinStyle(Qt::RoundJoin);
        p.setPen(checkPen);
        QPainterPath path;
        path.moveTo(box.left() + 3.5, box.top() + kBoxSize / 2.0);
        path.lineTo(box.left() + kBoxSize / 2.5, box.bottom() - 3.5);
        path.lineTo(box.right() - 3.0, box.top() + 3.5);
        p.drawPath(path);
    }

    if (!text().isEmpty()) {
        const QRect textRect(box.right() + kSpacing, 0,
                             width() - box.right() - kSpacing, height());
        QColor textColor = colors.windowText;
        if (!isEnabled()) {
            textColor.setAlpha(110);
        }
        p.setPen(textColor);
        p.drawText(textRect, Qt::AlignLeft | Qt::AlignVCenter, text());
    }
}

}  // namespace sli::toolkit
