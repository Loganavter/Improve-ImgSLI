#pragma once

#include <QListView>

namespace sli::toolkit::unified_flyout {

class MinimalistScrollBar;

// Overlay list view with Escape-to-close signal and custom MinimalistScrollBar.
// Mirrors Python's OverlayListView.
class OverlayListView : public QListView {
  Q_OBJECT

 public:
  explicit OverlayListView(QWidget* parent = nullptr);

 signals:
  void escapePressed();

 protected:
  void keyPressEvent(QKeyEvent* event) override;
  void resizeEvent(QResizeEvent* event) override;
  void paintEvent(QPaintEvent* event) override;
  bool eventFilter(QObject* obj, QEvent* event) override;

 private:
  void updateScrollbarVisibility();
  void positionScrollbar();
  void syncStepsFromNative();

  MinimalistScrollBar* scrollbar_ = nullptr;
  static constexpr int kScrollbarWidth = 10;
  static constexpr int kScrollbarGap = 0;
};

}  // namespace sli::toolkit::unified_flyout