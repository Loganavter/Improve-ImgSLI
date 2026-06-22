#pragma once

#include <QPair>
#include <QRect>
#include <QString>
#include <QWidget>

#include "sli/toolkit/overlays/in_window_overlay.h"

namespace sli::toolkit {

/// Overlay that paints two drop-zones (vertical split or horizontal split)
/// with accent-colored rounded rectangles and text labels.
/// Mirrors Python `DragDropOverlay` from `drag_drop_overlay.py`.
class DragDropOverlay final : public TopLevelInWindowOverlay {
    Q_OBJECT

public:
    explicit DragDropOverlay(QWidget* parent = nullptr);

    /// Update overlay state. If targetRect is null, hides the overlay.
    /// Otherwise sets geometry and paints two split-drop zones with
    /// the given text labels.
    void setOverlayState(
        bool visible,
        std::optional<QRect> targetRect,
        bool horizontal = false,
        const QString& text1 = {},
        const QString& text2 = {}
    );

protected:
    void paintEvent(QPaintEvent* event) override;

private:
    bool horizontal_ = false;
    QPair<QString, QString> texts_ = { {}, {} };
    std::optional<QRect> targetRect_;
};

}  // namespace sli::toolkit