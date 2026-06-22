#include "sli/toolkit/atomic/spin_box.h"

#include <QLineEdit>
#include <QPainter>
#include <QStyleOptionSpinBox>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

SpinBox::SpinBox(QWidget* parent)
    : QSpinBox(parent) {
    setButtonSymbols(QAbstractSpinBox::PlusMinus);
    setAlignment(Qt::AlignLeft | Qt::AlignVCenter);
    setMinimumHeight(28);
    setFrame(false);
    if (auto* edit = lineEdit()) {
        edit->setStyleSheet("background: transparent; border: none;");
        edit->setContentsMargins(8, 0, 4, 0);
    }
}

QSize SpinBox::sizeHint() const {
    QSize base = QSpinBox::sizeHint();
    base.setHeight(qMax(base.height(), 28));
    base.setWidth(qMax(base.width(), 72));
    return base;
}

void SpinBox::paintEvent(QPaintEvent* event) {
    const auto& colors = Theme::palette();

    {
        QPainter p(this);
        p.setRenderHint(QPainter::Antialiasing);
        QColor border = hasFocus() ? colors.accent : colors.border;
        p.setPen(QPen(border, hasFocus() ? 1.5 : 1.0));
        p.setBrush(colors.base);
        p.drawRoundedRect(rect().adjusted(1, 1, -1, -1), 4, 4);
    }

    QSpinBox::paintEvent(event);
}

}  // namespace sli::toolkit
