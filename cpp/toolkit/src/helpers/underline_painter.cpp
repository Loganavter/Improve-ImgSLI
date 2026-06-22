#include "sli/toolkit/helpers/underline_painter.h"
#include "sli/toolkit/theme.h"

#include <QLineEdit>
#include <QPainter>
#include <QPen>
#include <QPointF>
#include <QWidget>

#include <algorithm>
#include <cmath>
#include <numbers>

namespace sli::toolkit {

namespace {

constexpr int kTaperSegments = 24;

double widgetScale(const QRectF& rect)
{
    double h = static_cast<double>(rect.height());
    return std::max(1.0, h / 32.0);
}

void drawTaperedArc(
    QPainter& painter,
    const QColor& baseColor,
    double thickness,
    double cx,
    double cy,
    double radius,
    double startDeg,
    double sweepDeg,
    int fullAlpha,
    double alphaAtStart,
    double alphaAtEnd)
{
    QPen pen(baseColor);
    pen.setWidthF(thickness);
    pen.setCapStyle(Qt::FlatCap);

    std::optional<QPointF> prevPt;

    for (int s = 0; s <= kTaperSegments; ++s) {
        double t = static_cast<double>(s) / kTaperSegments;
        double ang = std::numbers::pi / 180.0 * (startDeg + sweepDeg * t);
        double x = cx + radius * std::cos(ang);
        double y = cy - radius * std::sin(ang);
        QPointF pt(x, y);

        if (prevPt.has_value()) {
            double tMid = (s - 0.5) / kTaperSegments;
            double alphaNorm = alphaAtStart + (alphaAtEnd - alphaAtStart) * tMid;
            int alphaVal = static_cast<int>(
                std::round(fullAlpha * std::clamp(alphaNorm, 0.0, 1.0)));
            QColor segColor(baseColor);
            segColor.setAlpha(alphaVal);
            pen.setColor(segColor);
            painter.setPen(pen);
            painter.drawLine(prevPt.value(), pt);
        }
        prevPt = pt;
    }
}

} // anonymous namespace

void drawBottomUnderline(
    QPainter& painter,
    const QRectF& rect,
    const UnderlineConfig& config,
    QWidget* deviceWidget)
{
    // Python dark-mode guard: in dark mode only draw on QLineEdit widgets.
    if (Theme::isDark()) {
        if (!deviceWidget || !qobject_cast<QLineEdit*>(deviceWidget))
            return;
    }

    // Build color list.
    std::vector<QColor> colors;
    if (config.color.has_value()) {
        colors.push_back(config.color.value());
    } else if (!config.colors.empty()) {
        colors = config.colors;
    } else {
        colors.emplace_back(Theme::getColor("button.default.bottom.edge"));
    }

    // Apply alpha override.
    if (config.alpha.has_value()) {
        for (auto& c : colors) {
            c.setAlpha(config.alpha.value());
        }
    }

    int count = static_cast<int>(colors.size());
    if (count == 0)
        return;

    double scale = widgetScale(rect);
    double arcRadius = config.arcRadius * scale;
    double thickness = config.thickness;
    double verticalOffset = config.verticalOffset * scale;

    double baseY = rect.bottom() - verticalOffset;
    double startX = rect.left();
    double endX = rect.right();
    double totalWidth = endX - startX;
    double segmentWidth = totalWidth / count;

    for (int i = 0; i < count; ++i) {
        const QColor& color = colors[i];

        QPen pen(color);
        pen.setWidthF(thickness);
        pen.setCapStyle(Qt::FlatCap);
        painter.setPen(pen);

        double segStart = startX + i * segmentWidth;
        double segEnd = startX + (i + 1) * segmentWidth;
        double lineStartX = (i == 0) ? (segStart + arcRadius) : segStart;
        double lineEndX = (i == count - 1) ? (segEnd - arcRadius) : segEnd;

        if (lineEndX > lineStartX) {
            painter.drawLine(QPointF(lineStartX, baseY), QPointF(lineEndX, baseY));
        }

        int fullAlpha = color.alpha();
        if (arcRadius <= 0.0)
            continue;

        if (i == 0) {
            // Left end: arc 180°→270°, alpha fades 0→full
            double cxx = startX + arcRadius;
            double cyy = baseY - arcRadius;
            drawTaperedArc(painter, color, thickness, cxx, cyy, arcRadius,
                           180.0, 90.0, fullAlpha, 0.0, 1.0);
        }

        if (i == count - 1) {
            // Right end: arc 270°→360°, alpha fades full→0
            double cxx = endX - arcRadius;
            double cyy = baseY - arcRadius;
            drawTaperedArc(painter, color, thickness, cxx, cyy, arcRadius,
                           270.0, 90.0, fullAlpha, 1.0, 0.0);
        }
    }
}

}  // namespace sli::toolkit