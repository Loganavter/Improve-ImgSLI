#pragma once

#include <QWidget>

#include <vector>

namespace sli::toolkit {
class Button;
class MinimalistScrollBar;
class ComboBox;
}  // namespace sli::toolkit

namespace sli::toolkit::comboboxes {

class DropdownItemSlot;

// DropdownOverlay — child QWidget that floats over the parent window.
// Mirrors Python's _DropdownOverlay.
// Used exclusively by ComboBox (the Button-based combobox).
//
class DropdownOverlay : public QWidget {
  Q_OBJECT

 public:
  static constexpr int kRadius = 8;
  static constexpr int kShadow = 10;

  explicit DropdownOverlay(sli::toolkit::ComboBox* owner, QWidget* parent);
  ~DropdownOverlay() override;

  // Show, position, and populate the overlay.
  void showForOwner();

  // Sync scrollbar range/value to current visible state.
  void syncScrollbar();

  // Rebind slot widgets to visible items at current scroll offset.
  void rebindSlots();

 protected:
  void paintEvent(QPaintEvent* event) override;
  void resizeEvent(QResizeEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;
  void mouseMoveEvent(QMouseEvent* event) override;
  void mouseReleaseEvent(QMouseEvent* event) override;
  void wheelEvent(QWheelEvent* event) override;

 private:
  int itemHeight() const;
  int visibleCount() const;
  int listHeight() const;
  QRect contentRect() const;
  bool hasScrollbar() const;
  QRect listRect() const;
  QRect itemRect(int visibleIndex) const;
  void ensureSlots(int count);
  void reposition();
  void positionScrollbar();
  bool forwardToScrollbar(QMouseEvent* event);
  void onScrollbarValueChanged(int value);
  void onSlotClicked(DropdownItemSlot* slot);

  sli::toolkit::ComboBox* owner_;
  std::vector<DropdownItemSlot*> slots_;
  sli::toolkit::MinimalistScrollBar* scrollbar_;

  static constexpr int kScrollbarWidth = 10;
};

}  // namespace sli::toolkit::comboboxes
