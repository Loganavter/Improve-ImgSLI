#include "sli/toolkit/button.h"

#include <QPainter>
#include <QStyleOptionButton>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

Button::Button(const QString& text, Variant variant, QWidget* parent)
    : QAbstractButton(parent),
      variant_(variant) {
    setText(text);
    setCursor(Qt::PointingHandCursor);
    setFocusPolicy(Qt::StrongFocus);
    setMinimumHeight(36);
}

QSize Button::sizeHint() const {
    const int width = fontMetrics().horizontalAdvance(text()) + 24;
    return {qMax(44, width), 36};
}

void Button::setVariant(Variant variant) {
    variant_ = variant;
    update();
}

void Button::paintEvent(QPaintEvent*) {
    const auto& colors = Theme::palette();
    QColor fill = colors.button;
    if (variant_ == Variant::Ghost) {
        fill = Qt::transparent;
    } else if (variant_ == Variant::Subtle) {
        fill = colors.window;
    } else if (variant_ == Variant::Default && isChecked()) {
        fill = colors.accent;
    }
    if (isDown()) {
        fill = colors.pressed;
    } else if (underMouse()) {
        fill = colors.hover;
    }

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setPen(QPen(
        hasFocus() ? colors.accent : colors.border,
        hasFocus() ? 1.5 : 1.0));
    painter.setBrush(fill);
    painter.drawRoundedRect(rect().adjusted(1, 1, -1, -1), 6, 6);
    painter.setPen(isEnabled() ? colors.buttonText : QColor(colors.buttonText.red(),
        colors.buttonText.green(), colors.buttonText.blue(), 110));
    painter.drawText(rect(), Qt::AlignCenter, text());
}

}  // namespace sli::toolkit
