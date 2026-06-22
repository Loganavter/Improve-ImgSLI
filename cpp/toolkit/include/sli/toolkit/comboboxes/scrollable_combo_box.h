#pragma once

#include <QString>
#include <QTimer>
#include <QVariant>
#include <QWidget>

#include <vector>

#include "sli/toolkit/comboboxes/models.h"

namespace sli::toolkit::comboboxes {

class Overlay;

class ScrollableComboBox : public QWidget {
  Q_OBJECT

 public:
  explicit ScrollableComboBox(QWidget* parent = nullptr);

  int count() const { return static_cast<int>(items_.size()); }
  int currentIndex() const { return currentIndex_; }
  QString currentText() const;
  QVariant currentData() const;

  void setText(const QString& text);
  void setCurrentIndex(int index);
  void updateState(int count, int currentIndex,
                   const QString& text = {},
                   const std::vector<QString>& items = {});

  void addItem(const QString& text, const QVariant& data = {});
  void setItems(std::vector<ComboItem> items);
  void clear();

  void setSearchEnabled(bool enabled);
  bool searchEnabled() const { return searchEnabled_; }

  void setAutoWidthEnabled(bool enabled);
  bool autoWidthEnabled() const { return autoWidth_; }

  QFont getItemFont() const { return font(); }
  int getItemHeight() const { return height() - 2; }

  QSize sizeHint() const override;

 signals:
  void currentIndexChanged(int index);
  void currentTextChanged(const QString& text);
  void wheelScrolledToIndex(int index);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;
  void wheelEvent(QWheelEvent* event) override;
  void keyPressEvent(QKeyEvent* event) override;
  void changeEvent(QEvent* event) override;

 private:
  void openOverlay();
  void onOverlaySelection(int index);
  void applyDebouncedIndex();
  void adjustWidthToContent();

  std::vector<ComboItem> items_;
  int currentIndex_ = -1;
  bool searchEnabled_ = false;
  bool autoWidth_ = false;
  Overlay* overlay_ = nullptr;
  QTimer* debounceTimer_ = nullptr;
  int pendingIndex_ = -1;
};

}  // namespace sli::toolkit::comboboxes
