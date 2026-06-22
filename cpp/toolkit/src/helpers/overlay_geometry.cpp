#include "sli/toolkit/helpers/overlay_geometry.h"

#include <QPoint>
#include <QRect>
#include <QSize>
#include <QWidget>

namespace sli::toolkit {

QRect calculateCenteredOverlayGeometry(
    const QWidget& anchorWidget,
    const QWidget& ownerWindow,
    const QSize& contentSize,
    int shadowRadius,
    int currentIndex,
    int visibleIndex,
    int rowHeight,
    bool scrollable)
{
    int outerWidth = contentSize.width() + shadowRadius * 2;
    int outerHeight = contentSize.height() + shadowRadius * 2;

    QRect comboRect = anchorWidget.rect();
    QPoint anchorCenter = anchorWidget.mapToGlobal(comboRect.center());
    QPoint ownerTopLeftGlobal = anchorWidget.mapToGlobal(comboRect.topLeft());
    QPoint windowTopLeftGlobal = ownerWindow.mapToGlobal(QPoint(0, 0));
    QRect windowGlobalRect(windowTopLeftGlobal, ownerWindow.size());

    if (currentIndex < 0)
        currentIndex = 0;
    if (visibleIndex < 0)
        visibleIndex = 0;

    int idealYGlobal;
    if (scrollable) {
        idealYGlobal = static_cast<int>(anchorCenter.y() - outerHeight / 2.0);
    } else {
        int selectedItemOffsetY = visibleIndex * rowHeight;
        idealYGlobal = static_cast<int>(
            anchorCenter.y() - selectedItemOffsetY - rowHeight / 2.0 - shadowRadius);
    }

    int idealXGlobal = static_cast<int>(ownerTopLeftGlobal.x() - shadowRadius);

    int finalXGlobal = std::max(
        windowGlobalRect.left(),
        std::min(idealXGlobal, windowGlobalRect.right() - outerWidth + 1));
    int finalYGlobal = std::max(
        windowGlobalRect.top(),
        std::min(idealYGlobal, windowGlobalRect.bottom() - outerHeight + 1));

    QPoint topLeft = ownerWindow.mapFromGlobal(QPoint(finalXGlobal, finalYGlobal));
    return QRect(topLeft.x(), topLeft.y(), outerWidth, outerHeight);
}

}  // namespace sli::toolkit