#include "sli/toolkit/atomic/spin_box.h"

#include <QFontMetrics>
#include <QKeyEvent>
#include <QPainter>
#include <QStyle>
#include <QTimer>
#include <QValidator>
#include <QWheelEvent>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

SpinBox::SpinBox(QWidget* parent,
                 int defaultValue,
                 Qt::Alignment alignment,
                 bool wheelRequiresFocus)
    : QLineEdit(parent),
      m_value(defaultValue),
      m_defaultValue(defaultValue),
      m_wheelRequiresFocus(wheelRequiresFocus) {
    setAlignment(alignment);
    setValidator(new QIntValidator(-999999, 999999, this));
    setText(QString::number(defaultValue));
    setMinimumWidth(minimumSizeHint().width());
    setFixedHeight(kFixedHeight);

    connect(this, &QLineEdit::editingFinished,
            this, &SpinBox::onEditingFinished);

    updateStyle();
}

void SpinBox::setRange(int minVal, int maxVal) {
    m_minimum = minVal;
    m_maximum = maxVal;
    setValue(m_value);
    setMinimumWidth(minimumSizeHint().width());
    updateGeometry();
}

void SpinBox::setValue(int val) {
    const int clamped = qBound(m_minimum, val, m_maximum);

    if (m_value != clamped) {
        m_value = clamped;
        emit valueChanged(m_value);
    }

    if (text() != QString::number(clamped)) {
        setText(QString::number(clamped));
    }
    updateGeometry();
}

QSize SpinBox::sizeHint() const {
    return QSize(contentWidth(), kFixedHeight);
}

QSize SpinBox::minimumSizeHint() const {
    return QSize(contentWidth(), kFixedHeight);
}

int SpinBox::contentWidth() const {
    int widest = 2;
    widest = qMax(widest, static_cast<int>(QString::number(m_minimum).length()));
    widest = qMax(widest, static_cast<int>(QString::number(m_maximum).length()));
    widest = qMax(widest, static_cast<int>(QString::number(m_value).length()));
    widest = qMax(widest, static_cast<int>(QString::number(m_defaultValue).length()));

    const QFontMetrics fm(fontMetrics());
    const int textWidth = fm.horizontalAdvance(QString("8").repeated(widest));
    const int margins = kHorizontalPadding * 2 + 14;
    return qMax(kMinimumWidth, textWidth + margins);
}

bool SpinBox::shouldHandleWheelEvent(const QWheelEvent*) const {
    return !m_wheelRequiresFocus || hasFocus();
}

void SpinBox::onEditingFinished() {
    const QString text = this->text().trimmed();
    int val = m_defaultValue;
    if (!text.isEmpty()) {
        bool ok = false;
        val = text.toInt(&ok);
        if (!ok) {
            val = m_defaultValue;
        }
    }
    setValue(val);
}

void SpinBox::wheelEvent(QWheelEvent* event) {
    if (!shouldHandleWheelEvent(event)) {
        return;
    }

    const int delta = event->angleDelta().y();
    if (delta == 0) {
        return;
    }

    const int step = (event->modifiers() & Qt::ShiftModifier) ? 10 : 1;

    if (delta > 0) {
        setValue(m_value + step);
    } else {
        setValue(m_value - step);
    }

    event->accept();
}

void SpinBox::keyPressEvent(QKeyEvent* event) {
    if (event->key() == Qt::Key_Up) {
        setValue(m_value + 1);
        event->accept();
    } else if (event->key() == Qt::Key_Down) {
        setValue(m_value - 1);
        event->accept();
    } else {
        QLineEdit::keyPressEvent(event);
    }
}

void SpinBox::focusInEvent(QFocusEvent* event) {
    QTimer::singleShot(0, this, QOverload<>::of(&QLineEdit::selectAll));
    QLineEdit::focusInEvent(event);
}

void SpinBox::updateStyle() {
    style()->unpolish(this);
    style()->polish(this);
    update();
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

    QLineEdit::paintEvent(event);
}

}  // namespace sli::toolkit
