#pragma once

#include <QPoint>
#include <QRect>
#include <QSize>

class QWidget;

namespace sli::toolkit::unified_flyout {

struct PlacementResult {
  QPoint topLeft;
  bool placedBelow = true;
};

PlacementResult computePlacement(QWidget* anchor, const QSize& flyoutSize,
                                 const QRect& screenAvailable);

}  // namespace sli::toolkit::unified_flyout
