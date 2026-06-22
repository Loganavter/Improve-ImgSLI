#pragma once

#include <QScrollBar>

namespace sli::toolkit::unified_flyout {

// Minimal port of Python's MinimalistScrollBar for unified_flyout use.
// Custom-painted vertical scrollbar with rounded pill handle, hover/drag
// thickness animation, and theme-aware idle/hover colors.
class MinimalistScrollBar : public QScrollBar {
  Q_OBJECT

 public:
  explicit MinimalistScrollBar(QWidget* parent = nullptr);

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

  bool hovered_ = false;
  bool dragging_ = false;
  int dragStartOffset_ = 0;

  QColor idleColor_;
  QColor hoverColor_;

  static constexpr int kIdleThickness = 4;
  static constexpr int kHoverThickness = 6;
  static constexpr int kDragThickness = 10;
  static constexpr int kMinHandleLength = 32;
  static constexpr int kPadding = 8;
};

}  // namespace sli::toolkit::unified_flyout