#include "sli/toolkit/comboboxes/overlay.h"

#include <QKeyEvent>
#include <QLineEdit>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPoint>
#include <Qt>
#include <QVBoxLayout>

#include <algorithm>

#include "sli/toolkit/comboboxes/search.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::comboboxes {

Overlay::Overlay(QWidget* parent)
    : QWidget(parent, Qt::Popup | Qt::FramelessWindowHint) {
  setAttribute(Qt::WA_TranslucentBackground);
  setFocusPolicy(Qt::StrongFocus);

  search_ = new QLineEdit(this);
  search_->setPlaceholderText(QStringLiteral("Search…"));
  search_->setVisible(false);
  connect(search_, &QLineEdit::textChanged, this, [this](const QString&) {
    applyFilter();
    update();
  });
}

void Overlay::setItems(std::vector<ComboItem> items) {
  items_ = std::move(items);
  applyFilter();
  hoveredIndex_ = visibleIndices_.empty() ? -1 : 0;
  relayout();
  update();
}

void Overlay::setSearchEnabled(bool enabled) {
  searchEnabled_ = enabled;
  search_->setVisible(enabled);
  relayout();
}

void Overlay::showForAnchor(QWidget* anchor) {
  applyFilter();
  relayout();
  if (anchor != nullptr) {
    const QPoint globalPos = anchor->mapToGlobal(QPoint(0, anchor->height()));
    move(globalPos);
    if (width() < anchor->width()) {
      resize(anchor->width(), height());
    }
  }
  if (searchEnabled_) {
    search_->clear();
    search_->setFocus(Qt::OtherFocusReason);
  }
  show();
}

void Overlay::applyFilter() {
  std::vector<QString> normalized;
  normalized.reserve(items_.size());
  for (const auto& item : items_) {
    normalized.push_back(item.normalizedText);
  }
  visibleIndices_ = visibleIndices(
      normalized, searchEnabled_,
      searchEnabled_ ? search_->text() : QString());
}

void Overlay::relayout() {
  int width = 160;
  QFontMetrics fm(font());
  for (const auto& item : items_) {
    width = std::max(width, fm.horizontalAdvance(item.text) + 32);
  }
  const int contentH =
      rowHeight_ * static_cast<int>(visibleIndices_.size()) + 8;
  const int totalH = (searchEnabled_ ? searchHeight_ : 0) + contentH;
  resize(width, std::max(rowHeight_, totalH));
  if (searchEnabled_) {
    search_->setGeometry(4, 4, width - 8, searchHeight_);
  }
}

int Overlay::indexAtPos(const QPoint& pos) const {
  const int yBase = searchEnabled_ ? (searchHeight_ + 4) : 4;
  const int idx = (pos.y() - yBase) / rowHeight_;
  if (idx < 0 || idx >= static_cast<int>(visibleIndices_.size())) {
    return -1;
  }
  return idx;
}

void Overlay::mousePressEvent(QMouseEvent* event) {
  const int visible = indexAtPos(event->pos());
  if (visible < 0) {
    hide();
    return;
  }
  const int realIdx = visibleIndices_[visible];
  emit itemSelected(realIdx, items_[realIdx].data);
  hide();
}

void Overlay::mouseMoveEvent(QMouseEvent* event) {
  const int idx = indexAtPos(event->pos());
  if (idx != hoveredIndex_) {
    hoveredIndex_ = idx;
    update();
  }
}

void Overlay::paintEvent(QPaintEvent*) {
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);

  const QColor bg = Theme::getColor(QStringLiteral("flyout.background"));
  const QColor border = Theme::getColor(QStringLiteral("flyout.border"));
  const QColor hoverBg = Theme::getColor(QStringLiteral("list_item.background.hover"));
  const QColor textColor = Theme::getColor(QStringLiteral("dialog.text"));

  // Background + border — rounded rect with Radius=8 (mirrors Python RADIUS).
  static constexpr int kOverlayRadius = 8;
  p.setPen(QPen(border, 1.0));
  p.setBrush(bg);
  p.drawRoundedRect(rect().adjusted(0, 0, -1, -1), kOverlayRadius, kOverlayRadius);

  const int yBase = searchEnabled_ ? (searchHeight_ + 4) : 4;
  p.setPen(textColor);
  for (std::size_t i = 0; i < visibleIndices_.size(); ++i) {
    const int realIdx = visibleIndices_[i];
    const QRect row(4, yBase + static_cast<int>(i) * rowHeight_, width() - 8,
                    rowHeight_);
    if (static_cast<int>(i) == hoveredIndex_) {
      // Python draws a rounded rect with RADIUS=6 on hover.
      p.save();
      p.setPen(Qt::NoPen);
      p.setBrush(hoverBg);
      p.drawRoundedRect(row.adjusted(0, 1, 0, -1), 6, 6);
      p.restore();
    }
    p.drawText(row.adjusted(8, 0, -8, 0), Qt::AlignVCenter | Qt::AlignLeft,
               items_[realIdx].text);
  }
}

void Overlay::keyPressEvent(QKeyEvent* event) {
  if (visibleIndices_.empty()) {
    QWidget::keyPressEvent(event);
    return;
  }
  const int size = static_cast<int>(visibleIndices_.size());
  if (event->key() == Qt::Key_Down) {
    hoveredIndex_ = (hoveredIndex_ + 1) % size;
    update();
  } else if (event->key() == Qt::Key_Up) {
    hoveredIndex_ = (hoveredIndex_ - 1 + size) % size;
    update();
  } else if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter) {
    if (hoveredIndex_ >= 0) {
      const int realIdx = visibleIndices_[hoveredIndex_];
      emit itemSelected(realIdx, items_[realIdx].data);
      hide();
    }
  } else if (event->key() == Qt::Key_Escape) {
    hide();
  } else {
    QWidget::keyPressEvent(event);
  }
}

void Overlay::hideEvent(QHideEvent* event) { QWidget::hideEvent(event); }

}  // namespace sli::toolkit::comboboxes
