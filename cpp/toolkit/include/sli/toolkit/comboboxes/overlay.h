#pragma once

#include <QString>
#include <QVariant>
#include <QWidget>

#include <vector>

#include "sli/toolkit/comboboxes/models.h"

class QLineEdit;

namespace sli::toolkit::comboboxes {

class Overlay : public QWidget {
  Q_OBJECT

 public:
  explicit Overlay(QWidget* parent = nullptr);

  void setItems(std::vector<ComboItem> items);
  void setSearchEnabled(bool enabled);
  void showForAnchor(QWidget* anchor);

  int currentIndex() const { return hoveredIndex_; }

 signals:
  void itemSelected(int index, const QVariant& data);

 protected:
  void paintEvent(QPaintEvent* event) override;
  void mousePressEvent(QMouseEvent* event) override;
  void mouseMoveEvent(QMouseEvent* event) override;
  void keyPressEvent(QKeyEvent* event) override;
  void hideEvent(QHideEvent* event) override;

 private:
  void applyFilter();
  void relayout();
  int indexAtPos(const QPoint& pos) const;

  std::vector<ComboItem> items_;
  std::vector<int> visibleIndices_;
  QLineEdit* search_ = nullptr;
  bool searchEnabled_ = false;
  int hoveredIndex_ = -1;
  int rowHeight_ = 28;
  int searchHeight_ = 24;
};

}  // namespace sli::toolkit::comboboxes
