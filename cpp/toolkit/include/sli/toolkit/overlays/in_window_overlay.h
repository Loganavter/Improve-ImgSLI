#pragma once

/// @file
/// Top-level in-window overlay infrastructure.
///
/// The overlay fills its parent window, stays inside Qt's normal widget
/// hierarchy, and can host arbitrary child widgets from this toolkit or
/// from the host app.

#include <QEvent>
#include <QLabel>
#include <QMap>
#include <QPoint>
#include <QRect>
#include <QSize>
#include <QString>
#include <QVector>
#include <QWidget>

#include <optional>

namespace sli::toolkit {

/// Relative widget placement around the anchor center.
/// Mirrors Python `OverlaySlot(Enum)` from `in_window_overlay.py`.
enum class OverlaySlot {
    CENTER,
    UP,
    DOWN,
    LEFT,
    RIGHT,
    UP_LEFT,
    UP_RIGHT,
    DOWN_LEFT,
    DOWN_RIGHT,
};

/// Direction vector for each OverlaySlot (dx, dy).
inline QPair<int, int> overlaySlotVector(OverlaySlot slot) {
    switch (slot) {
    case OverlaySlot::CENTER:    return { 0,  0};
    case OverlaySlot::UP:        return { 0, -1};
    case OverlaySlot::DOWN:      return { 0,  1};
    case OverlaySlot::LEFT:      return {-1,  0};
    case OverlaySlot::RIGHT:     return { 1,  0};
    case OverlaySlot::UP_LEFT:   return {-1, -1};
    case OverlaySlot::UP_RIGHT:  return { 1, -1};
    case OverlaySlot::DOWN_LEFT: return {-1,  1};
    case OverlaySlot::DOWN_RIGHT:return { 1,  1};
    }
    return {0, 0};
}

/// Registered child widget metadata. Mirrors Python `OverlayItem` dataclass.
struct OverlayItem {
    QString key;
    QWidget* widget = nullptr;
    std::optional<OverlaySlot> slot;
    std::optional<int> distance;
    std::optional<QRect> geometry;
};

/// A modal full-parent overlay that can host arbitrary widgets.
///
/// Widgets can be placed either in an ``OverlaySlot`` around the anchor
/// center or with an explicit geometry in overlay-local coordinates.
/// Mirrors Python `TopLevelInWindowOverlay` from `in_window_overlay.py`.
class TopLevelInWindowOverlay : public QWidget {
    Q_OBJECT

public:
    explicit TopLevelInWindowOverlay(
        QWidget* parent,
        QWidget* anchor = nullptr,
        bool closeOnBackground = true,
        bool closeOnEscape = true,
        bool closeOnDeactivate = true,
        int defaultDistance = 96
    );

    void setAnchor(QWidget* anchor);

    /// Add any child widget to the overlay.
    /// ``geometry`` takes precedence over slot placement. When no explicit
    /// geometry is supplied, the widget keeps its current size if valid,
    /// otherwise its ``sizeHint()`` is used.
    QWidget* addWidget(
        QWidget* widget,
        const QString& key = {},
        std::optional<OverlaySlot> slot = OverlaySlot::CENTER,
        std::optional<int> distance = std::nullopt,
        std::optional<QRect> geometry = std::nullopt
    );

    void removeWidget(QWidget* widget);
    void clearWidgets(bool deleteWidgets = false);

    QWidget* widgetForKey(const QString& key) const;
    QVector<OverlayItem> items() const { return items_; }

    void showOverlay();
    void dismiss(bool emitSignal = true);

signals:
    void dismissed();

protected:
    void hideEvent(QHideEvent* event) override;
    void resizeEvent(QResizeEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    void mousePressEvent(QMouseEvent* event) override;
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    void reposition();
    QSize itemSize(QWidget* widget) const;
    QPoint anchorCenter() const;
    QRect clampRect(QRect rect) const;
    void installFilters();
    void removeFilters();

    QWidget* anchor_ = nullptr;
    bool closeOnBackground_ = true;
    bool closeOnEscape_ = true;
    bool closeOnDeactivate_ = true;
    int defaultDistance_ = 96;

    QVector<OverlayItem> items_;
    bool filtersInstalled_ = false;
    QWidget* filterParent_ = nullptr;
    QWidget* filterWindow_ = nullptr;
};

}  // namespace sli::toolkit