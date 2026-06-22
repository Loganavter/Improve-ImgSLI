#include "sli/toolkit/atomic/radio_button.h"

#include <QEasingCurve>
#include <QEvent>
#include <QFocusEvent>
#include <QFontMetrics>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QTimer>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

RadioButton::RadioButton(const QString& text, QWidget* parent)
    : QAbstractButton(parent) {
    setText(text);
    setCheckable(true);
    setAutoExclusive(true);
    setCursor(Qt::PointingHandCursor);
    setFocusPolicy(Qt::StrongFocus);
    setMouseTracking(true);
    setAttribute(Qt::WA_Hover, true);
    setMinimumHeight(24);

    // Setup hover animation
    m_hoverAnim = new QPropertyAnimation(this, "hoverProgress", this);
    m_hoverAnim->setDuration(120);
    m_hoverAnim->setEasingCurve(QEasingCurve::OutCubic);
}

void RadioButton::setHoverProgress(qreal value) {
    m_hoverProgress = qBound(0.0, value, 1.0);
    update();
}

QSize RadioButton::sizeHint() const {
    const QFontMetrics fm(font());
    const int textWidth = text().isEmpty()
        ? 0
        : fm.horizontalAdvance(text());

    const int extra = 4;
    const int h = qMax(kIndicatorSize + 2 * kPaddingV,
                        fm.height() + 2 * kPaddingV);
    const int w = kPaddingH + kIndicatorSize +
                  (textWidth ? kSpacing : 0) + textWidth +
                  kPaddingH + extra;
    return QSize(w, h);
}

QSize RadioButton::minimumSizeHint() const {
    return sizeHint();
}

QRectF RadioButton::indicatorRect(const QRectF& fullRect) const {
    return QRectF(
        fullRect.x() + kPaddingH,
        fullRect.y() + (fullRect.height() - kIndicatorSize) / 2.0,
        kIndicatorSize,
        kIndicatorSize
    );
}

QRectF RadioButton::textRectAvailable(const QRectF& fullRect,
                                      const QRectF& indicatorRect) const {
    const qreal textLeft = indicatorRect.right() + kSpacing;
    const qreal availableW = qMax(0.0,
        fullRect.width() - (textLeft - fullRect.left()) - kPaddingH);
    return QRectF(textLeft, fullRect.y(), availableW, fullRect.height());
}

QRectF RadioButton::textRectContent(const QRectF& fullRect,
                                    const QRectF& indicatorRect) const {
    const QRectF avail = textRectAvailable(fullRect, indicatorRect);
    const QString textStr = text().isEmpty() ? "" : text();
    const QFontMetrics fm(font());
    const qreal contentW = qMin(avail.width(),
        static_cast<qreal>(fm.horizontalAdvance(textStr)));
    return QRectF(avail.left(), avail.top(), contentW, avail.height());
}

bool RadioButton::hoverHitTest(const QPointF& pos) const {
    const QRectF r(rect());
    const QRectF ind = indicatorRect(r);
    const QFontMetrics fm(font());
    const QRectF tx = textRectContent(r, ind);
    return ind.contains(pos) || tx.contains(pos);
}

void RadioButton::setHoverActive(bool active) {
    active = bool(active);
    if (m_hoverActive == active) {
        return;
    }
    m_hoverActive = active;
    animateHover(active);
}

void RadioButton::animateHover(bool hovered) {
    m_hoverAnim->stop();
    m_hoverAnim->setStartValue(m_hoverProgress);
    m_hoverAnim->setEndValue(hovered ? 1.0 : 0.0);
    m_hoverAnim->start();
}

bool RadioButton::event(QEvent* e) {
    if (e->type() == QEvent::HoverEnter || e->type() == QEvent::HoverMove) {
        const auto* he = static_cast<QHoverEvent*>(e);
        setHoverActive(hoverHitTest(he->position()));
        return true;
    } else if (e->type() == QEvent::HoverLeave) {
        setHoverActive(false);
        return true;
    }
    return QAbstractButton::event(e);
}

void RadioButton::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        const QRectF r(rect());
        const QRectF ind = indicatorRect(r);
        const QFontMetrics fm(font());
        const QRectF tx = textRectContent(r, ind);

        if (ind.contains(e->position()) || tx.contains(e->position())) {
            setChecked(true);
            e->accept();
            return;
        }
    }
    QAbstractButton::mouseReleaseEvent(e);
}

void RadioButton::focusInEvent(QFocusEvent* e) {
    QTimer::singleShot(0, this, QOverload<>::of(&QWidget::update));
    QAbstractButton::focusInEvent(e);
}

void RadioButton::focusOutEvent(QFocusEvent* e) {
    QTimer::singleShot(0, this, QOverload<>::of(&QWidget::update));
    QAbstractButton::focusOutEvent(e);
}

void RadioButton::changeEvent(QEvent* e) {
    update();
    QAbstractButton::changeEvent(e);
}

void RadioButton::paintEvent(QPaintEvent*) {
    const auto& colors = Theme::palette();

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);

    const QRectF rect(this->rect());
    const QFontMetrics fm(font());
    const QRectF indicatorRect = this->indicatorRect(rect);
    const QRectF textRectAvail = textRectAvailable(rect, indicatorRect);

    const QColor accent = colors.accent;
    const QColor border = colors.border;
    const QColor textColor = colors.windowText;
    const QColor neutralHover = colors.hover;
    const int disabledAlpha = kDisabledAlpha;

    const bool isDisabled = !isEnabled();
    const bool isChecked = this->isChecked();

    const QPointF center = indicatorRect.center();
    const qreal radius = indicatorRect.width() / 2.0;

    if (isChecked) {
        // Draw filled radio button (checked)
        const qreal innerFactor = kInnerHoleFactorBase +
            (kInnerHoleFactorHover - kInnerHoleFactorBase) * m_hoverProgress;
        const qreal innerR = radius * innerFactor;

        QPainterPath path;
        path.addEllipse(center, radius, radius);
        path.addEllipse(center, innerR, innerR);
        path.setFillRule(Qt::OddEvenFill);

        QColor fillColor = accent;
        if (isDisabled) {
            fillColor.setAlpha(disabledAlpha);
        }
        painter.setPen(Qt::NoPen);
        painter.setBrush(fillColor);
        painter.drawPath(path);

        QColor borderColor = border;
        if (isDisabled) {
            borderColor.setAlpha(disabledAlpha);
        }
        painter.setPen(QPen(borderColor, kOutlineWidth));
        painter.setBrush(Qt::NoBrush);
        painter.drawEllipse(center, radius, radius);
    } else {
        // Draw empty radio button (unchecked)
        QColor borderColor = border;
        if (isDisabled) {
            borderColor.setAlpha(disabledAlpha);
        }
        painter.setPen(QPen(borderColor, kOutlineWidth));

        if (m_hoverProgress > 0.001 && !isDisabled) {
            QColor hoverFill = neutralHover;
            int alpha = static_cast<int>(40 + 100 * m_hoverProgress);
            hoverFill.setAlpha(qBound(0, alpha, 255));
            painter.setBrush(hoverFill);
        } else {
            painter.setBrush(Qt::NoBrush);
        }
        painter.drawEllipse(center, radius, radius);
    }

    // Draw text
    if (!text().isEmpty()) {
        QColor drawTextColor = textColor;
        if (isDisabled) {
            drawTextColor.setAlpha(disabledAlpha);
        }
        painter.setPen(drawTextColor);

        QString fullText = text();
        if (fm.horizontalAdvance(fullText) > textRectAvail.width()) {
            fullText = fm.elidedText(
                fullText,
                Qt::ElideRight,
                static_cast<int>(textRectAvail.width())
            );
            painter.drawText(
                textRectAvail,
                Qt::AlignVCenter | Qt::AlignLeft,
                fullText
            );
        } else {
            const QRectF drawRect = textRectContent(rect, indicatorRect);
            painter.drawText(
                drawRect,
                Qt::AlignVCenter | Qt::AlignLeft,
                fullText
            );
        }
    }

    painter.end();
}

}  // namespace sli::toolkit
