#include "sli/toolkit/composite/unified_flyout/layout.h"

#include <QWidget>

namespace sli::toolkit::unified_flyout {

PlacementResult computePlacement(QWidget* anchor, const QSize& flyoutSize,
                                 const QRect& screenAvailable) {
  PlacementResult result;
  if (anchor == nullptr) {
    result.topLeft = screenAvailable.topLeft();
    return result;
  }
  const QPoint globalAnchor = anchor->mapToGlobal(QPoint(0, 0));
  const int spaceBelow =
      screenAvailable.bottom() - (globalAnchor.y() + anchor->height());
  const int spaceAbove = globalAnchor.y() - screenAvailable.top();

  if (spaceBelow >= flyoutSize.height() || spaceBelow >= spaceAbove) {
    result.topLeft = QPoint(globalAnchor.x(), globalAnchor.y() + anchor->height());
    result.placedBelow = true;
  } else {
    result.topLeft = QPoint(globalAnchor.x(), globalAnchor.y() - flyoutSize.height());
    result.placedBelow = false;
  }
  // Clamp into screen horizontally.
  const int maxX = screenAvailable.right() - flyoutSize.width();
  if (result.topLeft.x() > maxX) {
    result.topLeft.setX(maxX);
  }
  if (result.topLeft.x() < screenAvailable.left()) {
    result.topLeft.setX(screenAvailable.left());
  }
  return result;
}

}  // namespace sli::toolkit::unified_flyout
