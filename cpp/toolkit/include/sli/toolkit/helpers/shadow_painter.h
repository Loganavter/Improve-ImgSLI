#pragma once

#include <QRectF>

class QPainter;

namespace sli::toolkit {

/// Draw a stepped rounded shadow around a rectangle.
/// Mirrors Python `draw_rounded_shadow` from helper `shadow_painter.py`.
void drawRoundedShadow(
    QPainter& painter,
    const QRectF& rect,
    int steps,
    double radius,
    int alphaMax = 34);

}  // namespace sli::toolkit