#include "sli/toolkit/overlays/drag_drop_overlay.h"

#include <QPainter>
#include <QPainterPath>
#include <QPen>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

DragDropOverlay::DragDropOverlay(QWidget* parent)
    : TopLevelInWindowOverlay(
          parent,
          nullptr,      // no anchor
          false,        // closeOnBackground
          false,        // closeOnEscape
          false,        // closeOnDeactivate
          96
      )
{
    setAttribute(Qt::WA_TransparentForMouseEvents, true);
    setFocusPolicy(Qt::NoFocus);
}

void DragDropOverlay::setOverlayState(
    bool visible,
    std::optional<QRect> targetRect,
    bool horizontal,
    const QString& text1,
    const QString& text2
) {
    if (!targetRect.has_value()) {
        hide();
        return;
    }

    const QRect rect = targetRect.value();
    const bool stateChanged = (horizontal_ != horizontal)
        || (texts_.first != text1 || texts_.second != text2)
        || (geometry() != rect)
        || (isVisible() != visible);

    horizontal_ = horizontal;
    texts_ = { text1, text2 };
    targetRect_ = rect;
    setGeometry(rect);

    if (visible) {
        raise();
        QWidget::show();
    } else {
        hide();
    }

    if (stateChanged && visible)
        update();
}

void DragDropOverlay::paintEvent(QPaintEvent*) {
    if (!isVisible())
        return;

    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setRenderHint(QPainter::TextAntialiasing, true);

    QFont font = this->font();
    font.setPixelSize(20);
    font.setBold(true);
    painter.setFont(font);

    const double margin = 10.0;
    const double halfMargin = margin / 2.0;
    const double width = static_cast<double>(this->width());
    const double height = static_cast<double>(this->height());

    QVector<QRectF> rects;
    if (horizontal_) {
        const double halfHeight = height / 2.0;
        rects.append(QRectF(
            margin, margin,
            qMax(1.0, width - 2.0 * margin),
            qMax(1.0, halfHeight - margin - halfMargin)
        ));
        rects.append(QRectF(
            margin, halfHeight + halfMargin,
            qMax(1.0, width - 2.0 * margin),
            qMax(1.0, halfHeight - margin - halfMargin)
        ));
    } else {
        const double halfWidth = width / 2.0;
        rects.append(QRectF(
            margin, margin,
            qMax(1.0, halfWidth - margin - halfMargin),
            qMax(1.0, height - 2.0 * margin)
        ));
        rects.append(QRectF(
            halfWidth + halfMargin, margin,
            qMax(1.0, halfWidth - margin - halfMargin),
            qMax(1.0, height - 2.0 * margin)
        ));
    }

    const QColor accent = Theme::getColor(QStringLiteral("accent"));
    QColor fill(accent);
    fill.setAlpha(153);
    const QColor border = Theme::getColor(QStringLiteral("HighlightedText"));
    const QColor textColor = border;

    QPen pen(QColor(border), 1.25);
    pen.setJoinStyle(Qt::RoundJoin);
    painter.setPen(pen);
    painter.setBrush(fill);

    const QStringList texts = { texts_.first, texts_.second };
    for (int i = 0; i < rects.size(); ++i) {
        QPainterPath path;
        path.addRoundedRect(rects[i], 10.0, 10.0);
        painter.drawPath(path);

        painter.setPen(textColor);
        painter.drawText(
            rects[i].adjusted(15.0, 15.0, -15.0, -15.0),
            Qt::AlignCenter | Qt::TextWordWrap,
            texts[i]
        );
        painter.setPen(pen);
    }
}

}  // namespace sli::toolkit