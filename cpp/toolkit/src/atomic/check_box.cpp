#include "sli/toolkit/atomic/check_box.h"

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

CheckBox::CheckBox(const QString& text, QWidget* parent)
    : QAbstractButton(parent) {
    setText(text);
    setCheckable(true);
    setCursor(Qt::PointingHandCursor);
    setFocusPolicy(Qt::StrongFocus);
    setMouseTracking(true);
    setAttribute(Qt::WA_Hover, true);
    setMinimumHeight(24);

    m_checkedProgress = isChecked() ? 1.0 : 0.0;

    // Setup hover animation
    m_hoverAnim = new QPropertyAnimation(this, "hoverProgress", this);
    m_hoverAnim->setDuration(120);
    m_hoverAnim->setEasingCurve(QEasingCurve::OutCubic);

    // Setup checked animation
    m_checkedAnim = new QPropertyAnimation(this, "checkedProgress", this);
    m_checkedAnim->setDuration(150);
    m_checkedAnim->setEasingCurve(QEasingCurve::OutCubic);

    connect(this, &QAbstractButton::toggled,
            this, [this](bool) {
                const Qt::CheckState state = isChecked() ? Qt::Checked : Qt::Unchecked;
                onStateChanged(static_cast<int>(state));
            });
}

void CheckBox::setHoverProgress(qreal value) {
    m_hoverProgress = qBound(0.0, value, 1.0);
    update();
}

void CheckBox::setCheckedProgress(qreal value) {
    m_checkedProgress = qBound(0.0, value, 1.0);
    update();
}

QSize CheckBox::sizeHint() const {
    const QFontMetrics fm(font());
    const int textWidth = text().isEmpty()
        ? 0
        : fm.horizontalAdvance(text()) + 10;
    const int h = qMax(kIndicatorSize + 2 * kPaddingV,
                        fm.height() + 2 * kPaddingV);
    const int w = kPaddingH + kIndicatorSize +
                  (textWidth ? kSpacing : 0) + textWidth + kPaddingH;
    return QSize(w, h);
}

QSize CheckBox::minimumSizeHint() const {
    return sizeHint();
}

QRectF CheckBox::indicatorRect(const QRectF& fullRect) const {
    return QRectF(
        fullRect.x() + kPaddingH,
        fullRect.y() + (fullRect.height() - kIndicatorSize) / 2.0,
        kIndicatorSize,
        kIndicatorSize
    );
}

QRectF CheckBox::textRectAvailable(const QRectF& fullRect,
                                    const QRectF& indicatorRect) const {
    const qreal textLeft = indicatorRect.right() + kSpacing;
    const qreal availableW = qMax(0.0,
        width() - textLeft - kPaddingH);
    return QRectF(textLeft, fullRect.y(), availableW, fullRect.height());
}

QRectF CheckBox::textRectContent(const QRectF& fullRect,
                                  const QRectF& indicatorRect) const {
    const QRectF avail = textRectAvailable(fullRect, indicatorRect);
    const QString textStr = text().isEmpty() ? "" : text();
    const QFontMetrics fm(font());
    const qreal contentW = qMin(avail.width(),
        static_cast<qreal>(fm.horizontalAdvance(textStr)));
    return QRectF(avail.left(), avail.top(), contentW, avail.height());
}

bool CheckBox::hoverHitTest(const QPointF& pos) const {
    const QRectF r(rect());
    const QRectF ind = indicatorRect(r);
    const QFontMetrics fm(font());
    const QRectF tx = textRectContent(r, ind);
    return ind.contains(pos) || tx.contains(pos);
}

void CheckBox::setHoverActive(bool active) {
    active = bool(active);
    if (m_hoverActive == active) {
        return;
    }
    m_hoverActive = active;
    animateHover(active);
}

void CheckBox::animateHover(bool hovered) {
    m_hoverAnim->stop();
    m_hoverAnim->setStartValue(m_hoverProgress);
    m_hoverAnim->setEndValue(hovered ? 1.0 : 0.0);
    m_hoverAnim->start();
}

void CheckBox::onStateChanged(int state) {
    const qreal target = (state != Qt::Unchecked) ? 1.0 : 0.0;
    m_checkedAnim->stop();
    m_checkedAnim->setStartValue(m_checkedProgress);
    m_checkedAnim->setEndValue(target);
    m_checkedAnim->start();
}

bool CheckBox::event(QEvent* e) {
    if (e->type() == QEvent::HoverEnter || e->type() == QEvent::HoverMove) {
        const auto* he = static_cast<QHoverEvent*>(e);
        setHoverActive(hoverHitTest(he->position()));
        return true;
    } else if (e->type() == QEvent::HoverLeave && m_hoverProgress > 0) {
        setHoverActive(false);
        return true;
    }
    return QAbstractButton::event(e);
}

void CheckBox::mouseReleaseEvent(QMouseEvent* e) {
    if (e->button() == Qt::LeftButton) {
        const QRectF r(rect());
        const QRectF ind = indicatorRect(r);
        const QFontMetrics fm(font());
        const QRectF tx = textRectContent(r, ind);

        if (ind.contains(e->position()) || tx.contains(e->position())) {
            setChecked(!isChecked());
            e->accept();
            return;
        }
    }
    QAbstractButton::mouseReleaseEvent(e);
}

void CheckBox::focusInEvent(QFocusEvent* e) {
    QTimer::singleShot(0, this, QOverload<>::of(&QWidget::update));
    QAbstractButton::focusInEvent(e);
}

void CheckBox::focusOutEvent(QFocusEvent* e) {
    QTimer::singleShot(0, this, QOverload<>::of(&QWidget::update));
    QAbstractButton::focusOutEvent(e);
}

void CheckBox::changeEvent(QEvent* e) {
    update();
    QAbstractButton::changeEvent(e);
}

void CheckBox::paintEvent(QPaintEvent*) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);

    const QRectF rect(this->rect());
    const QFontMetrics fm(font());
    const QRectF indicatorRect = this->indicatorRect(rect);
    const QRectF textRectAvail = textRectAvailable(rect, indicatorRect);

    const QColor accent = Theme::getColor(QStringLiteral("accent"));
    const QColor border = Theme::getColor(QStringLiteral("dialog.border"));
    const QColor textColor = Theme::getColor(QStringLiteral("dialog.text"));
    const QColor neutralHover = Theme::getColor(QStringLiteral("dialog.button.hover"));
    const int disabledAlpha = kDisabledAlpha;

    const bool isDisabled = !isEnabled();
    const bool isChecked = this->isChecked();
    const bool isIndeterminate = false; // QAbstractButton doesn't support indeterminate state

    if (isChecked || isIndeterminate) {
        // Draw checked/indeterminate box
        QColor borderColor = border;
        if (isDisabled) {
            borderColor.setAlpha(disabledAlpha);
        }
        painter.setPen(QPen(borderColor, kOutlineWidth));

        QColor accentFill = accent;
        int baseAlpha = static_cast<int>(120 + 135 * m_checkedProgress);
        if (isDisabled) {
            baseAlpha = static_cast<int>(baseAlpha * 0.6);
        }
        accentFill.setAlpha(qBound(0, baseAlpha, 255));
        painter.setBrush(accentFill);
        painter.drawRoundedRect(indicatorRect, kIndicatorRadius, kIndicatorRadius);
    } else {
        // Draw unchecked box
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
        painter.drawRoundedRect(indicatorRect, kIndicatorRadius, kIndicatorRadius);
    }

    // Draw check mark or dash
    if (isChecked || isIndeterminate) {
        QColor glyphColor = Qt::white;
        if (isDisabled) {
            glyphColor.setAlpha(disabledAlpha);
        }

        if (isChecked) {
            painter.save();
            const QPointF center = indicatorRect.center();
            painter.translate(center);
            painter.rotate(kCheckRotationDeg);
            painter.translate(-center);

            painter.setPen(QPen(
                glyphColor,
                kCheckStrokeWidth,
                Qt::SolidLine,
                Qt::RoundCap,
                Qt::MiterJoin
            ));

            const qreal x1 = indicatorRect.left() +
                indicatorRect.width() * kCheckX1;
            const qreal y1 = indicatorRect.top() +
                indicatorRect.height() * kCheckY1Norm;
            const qreal x2 = indicatorRect.left() +
                indicatorRect.width() * kCheckX2;
            const qreal y2Pre = indicatorRect.top() +
                indicatorRect.height() * kCheckY2Pre;
            const qreal x3 = indicatorRect.left() +
                indicatorRect.width() * kCheckX3;
            const qreal y3Pre = indicatorRect.top() +
                indicatorRect.height() * kCheckY3Pre;

            const qreal cx = indicatorRect.center().y();
            const qreal y2 = cx + kCheckBottomFactor * (y2Pre - cx);
            const qreal y3 = cx + kCheckTopFactor * (y3Pre - cx);

            QPainterPath path;
            path.moveTo(QPointF(x1, y1));
            path.lineTo(QPointF(x2, y2));
            path.lineTo(QPointF(x3, y3));
            painter.drawPath(path);
            painter.restore();
        } else {
            // Draw dash for indeterminate state
            painter.setPen(QPen(
                glyphColor,
                kCheckStrokeWidth,
                Qt::SolidLine,
                Qt::RoundCap,
                Qt::MiterJoin
            ));
            const qreal lineMargin = indicatorRect.height() * 0.32;
            const qreal y = indicatorRect.center().y();
            const qreal x1 = indicatorRect.left() + lineMargin;
            const qreal x2 = indicatorRect.right() - lineMargin;
            painter.drawLine(QPointF(x1, y), QPointF(x2, y));
        }
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
            const QRectF drawRect(
                textRectAvail.left(),
                textRectAvail.top(),
                static_cast<qreal>(fm.horizontalAdvance(fullText)),
                textRectAvail.height()
            );
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
