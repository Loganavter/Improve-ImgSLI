#pragma once

#include <QColor>
#include <QRectF>

#include <optional>
#include <vector>

class QPainter;
class QWidget;

namespace sli::toolkit {

struct UnderlineConfig {
    double thickness = 0.15;
    double verticalOffset = 0.75;
    double arcRadius = 1.33;
    std::optional<int> alpha;
    std::optional<QColor> color;
    std::vector<QColor> colors;
};

/// Draw a bottom underline with optional tapered arcs at ends.
/// Mirrors Python `draw_bottom_underline()` from `underline_painter.py`.
/// deviceWidget is the QPainter's device cast to QWidget* for
/// the dark-mode QLineEdit guard. Can be nullptr.
void drawBottomUnderline(
    QPainter& painter,
    const QRectF& rect,
    const UnderlineConfig& config = UnderlineConfig{},
    QWidget* deviceWidget = nullptr);

}  // namespace sli::toolkit