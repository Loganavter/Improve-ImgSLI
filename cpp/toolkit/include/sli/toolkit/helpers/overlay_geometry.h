#pragma once

#include <QRect>
#include <QSize>

class QWidget;

namespace sli::toolkit {

/// Calculate geometry for a centered overlay widget.
/// Mirrors Python `calculate_centered_overlay_geometry()` from `overlay_geometry.py`.
QRect calculateCenteredOverlayGeometry(
    const QWidget& anchorWidget,
    const QWidget& ownerWindow,
    const QSize& contentSize,
    int shadowRadius,
    int currentIndex,
    int visibleIndex,
    int rowHeight,
    bool scrollable);

}  // namespace sli::toolkit