#include "sli/toolkit/helpers/shadow_painter.h"

#include <QPainter>
#include <QColor>

namespace sli::toolkit {

void drawRoundedShadow(
    QPainter& painter,
    const QRectF& rect,
    int steps,
    double radius,
    int alphaMax)
{
    painter.setPen(Qt::NoPen);
    for (int i = 0; i < steps; ++i) {
        double t = static_cast<double>(i) / steps;
        int alpha = static_cast<int>(alphaMax * (1.0 - t) * (1.0 - t));
        painter.setBrush(QColor(0, 0, 0, alpha));
        QRectF shadowRect = rect.adjusted(-i, -i + 1, i, i + 1);
        painter.drawRoundedRect(shadowRect, radius + i, radius + i);
    }
}

}  // namespace sli::toolkit