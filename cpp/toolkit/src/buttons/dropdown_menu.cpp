#include "sli/toolkit/buttons/dropdown_menu.h"

#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <Qt>

#include <algorithm>

#include "sli/toolkit/theme.h"

namespace sli::toolkit::buttons {

DropdownMenu::DropdownMenu(QWidget* parent)
    : QWidget(parent, Qt::Popup | Qt::FramelessWindowHint) {
  setAttribute(Qt::WA_TranslucentBackground);
  setFocusPolicy(Qt::StrongFocus);
}

void DropdownMenu::setActions(std::vector<MenuItem> items) {
  items_ = std::move(items);
  hoveredIndex_ = items_.empty() ? -1 : 0;
  layoutItems();
  update();
}

void DropdownMenu::showForAnchor(QWidget* anchor) {
  layoutItems();
  if (anchor != nullptr) {
    const QPoint globalPos = anchor->mapToGlobal(QPoint(0, anchor->height()));
    move(globalPos);
  }
  show();
  setFocus(Qt::OtherFocusReason);
}

void DropdownMenu::layoutItems() {
  int width = 120;
  QFontMetrics fm(font());
  for (const auto& [label, _] : items_) {
    width = std::max(width, fm.horizontalAdvance(label) + 24);
  }
  const int height = rowHeight_ * static_cast<int>(items_.size()) + 4;
  resize(width, std::max(rowHeight_, height));
}

void DropdownMenu::mousePressEvent(QMouseEvent* event) {
  const int idx = (event->position().y() - 2) / rowHeight_;
  if (idx >= 0 && idx < static_cast<int>(items_.size())) {
    emit itemSelected(items_[idx].second);
  }
  hide();
}

void DropdownMenu::paintEvent(QPaintEvent*) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);
  const Palette& palette = Theme::palette();
  p.setPen(palette.border);
  p.setBrush(palette.base);
  p.drawRoundedRect(rect().adjusted(0, 0, -1, -1), 6, 6);
  p.setPen(palette.windowText);
  for (std::size_t i = 0; i < items_.size(); ++i) {
    const QRect row(2, 2 + static_cast<int>(i) * rowHeight_, width() - 4,
                    rowHeight_);
    if (static_cast<int>(i) == hoveredIndex_) {
      p.fillRect(row, palette.hover);
    }
    p.drawText(row.adjusted(8, 0, -8, 0), Qt::AlignVCenter | Qt::AlignLeft,
               items_[i].first);
  }
}

void DropdownMenu::keyPressEvent(QKeyEvent* event) {
  if (items_.empty()) {
    QWidget::keyPressEvent(event);
    return;
  }
  if (event->key() == Qt::Key_Down) {
    hoveredIndex_ = (hoveredIndex_ + 1) % static_cast<int>(items_.size());
    update();
  } else if (event->key() == Qt::Key_Up) {
    hoveredIndex_ = (hoveredIndex_ - 1 + static_cast<int>(items_.size())) %
                    static_cast<int>(items_.size());
    update();
  } else if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
    if (hoveredIndex_ >= 0) {
      emit itemSelected(items_[hoveredIndex_].second);
    }
    hide();
  } else if (event->key() == Qt::Key_Escape) {
    hide();
  } else {
    QWidget::keyPressEvent(event);
  }
}

}  // namespace sli::toolkit::buttons
