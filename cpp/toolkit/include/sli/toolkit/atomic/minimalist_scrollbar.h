#pragma once

#include <QScrollBar>
#include <QColor>

namespace sli::toolkit {

// Minimal custom-painted QScrollBar with animated thickness on hover/drag.
// Supports both Vertical and Horizontal orientation.
// Features: rounded pill-shaped handle, theme-aware colors, smooth transitions.
// Mirrors Python atomic/minimalist_scrollbar.py.
class MinimalistScrollBar final : public QScrollBar {
  Q_OBJECT

 public:
  explicit MinimalistScrollBar(Qt::Orientation orientation = Qt::Vertical,
                               QWidget* parent = nullptr);

  // Register this scrollbar for hover tracking.
  // Called internally by constructor but exposed for flexibility.
  void registerHoverTracking();

  // Hit test for external hover managers (e.g., unity_hover_manager).
  // Returns true if pos is within scrollbar bounds.
  bool hoverHitTest(const QPoint& pos) const;

  // Set hover state explicitly (used by hover managers).
  void setHoverActive(bool active);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void enterEvent(QEnterEvent* event) override;
  void leaveEvent(QEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;
  void mouseMoveEvent(QMouseEvent* event) override;
  void mouseReleaseEvent(QMouseEvent* event) override;

 private:
  QRect handleRect() const;
  void updateColors();

  static constexpr int kIdleThickness = 4;
  static constexpr int kHoverThickness = 6;
  static constexpr int kDragThickness = 10;
  static constexpr int kMinHandleLength = 32;
  static constexpr int kPadding = 8;

  bool isDragging_ = false;
  int dragStartOffset_ = 0;
  bool isHovered_ = false;

  QColor idleColor_;
  QColor hoverColor_;
};

}  // namespace sli::toolkit
