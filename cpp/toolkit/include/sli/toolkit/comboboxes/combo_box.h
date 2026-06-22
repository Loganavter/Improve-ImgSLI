#pragma once

#include <QSize>
#include <QVariant>
#include <QWidget>

#include <memory>
#include <unordered_map>
#include <vector>

#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/comboboxes/models.h"

namespace sli::toolkit::comboboxes {
class DropdownOverlay;
}  // namespace sli::toolkit::comboboxes

namespace sli::toolkit {

// ComboBox — mirrors Python's ComboBox that inherits from Button.
//
// Architecture:
//   - Inherits Button (NOT QComboBox) — same as Python
//   - Custom paint: _ComboFieldBgLayer + _ComboFieldContentLayer on top of
//     Button's ripple layer
//   - DropdownOverlay: child QWidget with Button-slots + MinimalistScrollBar
//   - Full search system: normalizeForSearch / matchScore / visibleIndices
//   - flyout.background when expanded (mirrors Python _ComboFieldBgLayer)
//
class ComboBox final : public Button {
  Q_OBJECT

 public:
  static constexpr int kBaseHeight = 33;
  static constexpr int kRadius = 6;
  static constexpr int kItemVerticalPadding = 12;
  static constexpr int kTextHorizontalPadding = 12;

  explicit ComboBox(QWidget* parent = nullptr,
                    bool wheelRequiresFocus = false);
  ~ComboBox() override;

  // ---- item management ----
  int count() const;
  void addItem(const QString& text, const QVariant& data = {});
  void addItems(const QStringList& texts);
  void insertItem(int index, const QString& text, const QVariant& data = {});
  void removeItem(int index);
  void clear();

  // ---- accessors ----
  int currentIndex() const;
  QString currentText() const;
  QVariant currentData() const;
  QString itemText(int index) const;
  QVariant itemData(int index) const;
  int findText(const QString& text) const;
  int findData(const QVariant& data) const;
  QList<QPair<QString, QVariant>> items() const;

  // ---- mutators ----
  void setCurrentIndex(int index);
  void setCurrentText(const QString& text);
  void setCurrentData(const QVariant& data);
  void setItemText(int index, const QString& text);
  void setItemData(int index, const QVariant& data);

  // ---- size / layout ----
  void setMaxVisibleItems(int count);
  int maxVisibleItems() const;
  void setMinimumContentsLength(int count);
  void setSizeAdjustPolicy(int /*policy*/) {}  // no-op, mirrors Python

  QSize sizeHint() const override;
  QSize minimumSizeHint() const override;

  // ---- search ----
  void setSearchEnabled(bool enabled);
  bool isSearchEnabled() const;
  QString searchText() const;
  void clearSearch();

  // ---- dropdown ----
  void showDropdown();
  void hideDropdown();
  bool isExpanded() const;

  // ---- internal helpers used by DropdownOverlay ----
  int itemHeight() const;
  int scrollOffset() const { return scrollOffset_; }
  void setScrollOffset(int offset);
  const std::vector<comboboxes::ComboItem>& internalItems() const { return items_; }
  std::vector<int> visibleIndices() const;
  int visibleItemCount() const;
  int visiblePositionForIndex(int index) const;
  void ensureCurrentVisible();

 signals:
  void currentIndexChanged(int index);
  void currentTextChanged(const QString& text);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void keyPressEvent(QKeyEvent* event) override;
  void wheelEvent(QWheelEvent* event) override;
  void focusOutEvent(QFocusEvent* event) override;
  bool eventFilter(QObject* watched, QEvent* event) override;

 private:
  // search helpers
  void setSearchTextInternal(const QString& text);
  bool moveVisibleSelection(int step);
  void invalidateVisibleCache();

  // overlay management
  void ensureOverlay();
  void onFieldClicked();
  bool isDropdownWidget(QWidget* widget) const;
  void hideDropdownIfFocusLeft();

  // content width for sizeHint
  int contentWidthHint() const;

  std::vector<comboboxes::ComboItem> items_;
  int currentIndex_ = -1;
  bool expanded_ = false;
  int maxVisibleItems_ = 12;
  int minimumContentsLength_ = 0;
  int scrollOffset_ = 0;

  bool searchEnabled_ = true;
  QString searchText_;

  // visible-indices cache
  mutable bool visibleCacheDirty_ = true;
  mutable std::vector<int> visibleIndicesCache_;
  mutable std::unordered_map<int, int> visiblePositionsCache_;

  // overlay
  std::unique_ptr<comboboxes::DropdownOverlay> overlay_;
  QWidget* overlayParent_ = nullptr;
};

}  // namespace sli::toolkit
