#pragma once

#include <QString>
#include <QVariant>
#include <QWidget>

#include <utility>
#include <vector>

namespace sli::toolkit::buttons {

// Minimal dropdown menu for MenuCapability. Full implementation (positioning,
// keyboard navigation, theme-aware paint) belongs to a D5 follow-up; the
// current shell renders a flat QListWidget-style popup and emits actions when
// items are selected.
class DropdownMenu : public QWidget {
  Q_OBJECT

 public:
  using MenuItem = std::pair<QString, QVariant>;

  explicit DropdownMenu(QWidget* parent = nullptr);

  void setActions(std::vector<MenuItem> items);
  void showForAnchor(QWidget* anchor);

 signals:
  void itemSelected(const QVariant& data);

 protected:
  void mousePressEvent(QMouseEvent* event) override;
  void paintEvent(QPaintEvent* event) override;
  void keyPressEvent(QKeyEvent* event) override;

 private:
  void layoutItems();

  std::vector<MenuItem> items_;
  int hoveredIndex_ = -1;
  int rowHeight_ = 28;
};

}  // namespace sli::toolkit::buttons
