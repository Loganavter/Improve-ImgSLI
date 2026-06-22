#include "sli/toolkit/comboboxes/scrollable_combo_box.h"

#include <QFontMetrics>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPen>
#include <QPoint>
#include <Qt>
#include <QWheelEvent>

#include <algorithm>

#include "sli/toolkit/comboboxes/overlay.h"
#include "sli/toolkit/comboboxes/search.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::comboboxes {

namespace {
constexpr int kBaseHeight = 33;
constexpr int kRadius = 6;
constexpr int kTextHPad = 12;
constexpr int kArrowRightMargin = 14;
constexpr int kDebounceMs = 300;
}  // namespace

ScrollableComboBox::ScrollableComboBox(QWidget* parent) : QWidget(parent) {
  // Python's ScrollableComboBox inherits from Button which does NOT set a
  // cursor override.  Match that — no PointingHandCursor here.
  setFocusPolicy(Qt::StrongFocus);
  setMinimumWidth(0);
  overlay_ = new Overlay(this);
  connect(overlay_, &Overlay::itemSelected, this,
          [this](int index, const QVariant&) { onOverlaySelection(index); });

  debounceTimer_ = new QTimer(this);
  debounceTimer_->setSingleShot(true);
  debounceTimer_->setInterval(kDebounceMs);
  connect(debounceTimer_, &QTimer::timeout, this,
          &ScrollableComboBox::applyDebouncedIndex);
}

// ---------------------------------------------------------------------------
// auto-width
// ---------------------------------------------------------------------------

void ScrollableComboBox::setAutoWidthEnabled(bool enabled) {
  autoWidth_ = enabled;
  if (autoWidth_) {
    QTimer::singleShot(0, this, [this] { adjustWidthToContent(); });
  }
}

void ScrollableComboBox::adjustWidthToContent() {
  if (!autoWidth_) {
    return;
  }
  QFontMetrics fm(getItemFont());
  int maxTextW = 0;
  for (const auto& item : items_) {
    maxTextW = std::max(maxTextW, fm.horizontalAdvance(item.text));
  }
  maxTextW = std::max(maxTextW, fm.horizontalAdvance(currentText()));
  const int needed = std::max(80, maxTextW + 60);
  if (width() != needed) {
    setFixedWidth(needed);
    updateGeometry();
  }
}

// ---------------------------------------------------------------------------
// state
// ---------------------------------------------------------------------------

QString ScrollableComboBox::currentText() const {
  if (currentIndex_ < 0 || currentIndex_ >= static_cast<int>(items_.size())) {
    return {};
  }
  return items_[currentIndex_].text;
}

QVariant ScrollableComboBox::currentData() const {
  if (currentIndex_ < 0 || currentIndex_ >= static_cast<int>(items_.size())) {
    return {};
  }
  return items_[currentIndex_].data;
}

void ScrollableComboBox::setText(const QString& text) {
  // Python's setText updates the display text without changing the index.
  // We store it on the current item if one exists, or keep a pending text.
  if (currentIndex_ >= 0 && currentIndex_ < static_cast<int>(items_.size())) {
    items_[currentIndex_].text = text;
    items_[currentIndex_].normalizedText = normalizeForSearch(text);
  }
  update();
  if (autoWidth_) {
    QTimer::singleShot(0, this, [this] { adjustWidthToContent(); });
  }
}

void ScrollableComboBox::setCurrentIndex(int index) {
  if (index == currentIndex_) {
    return;
  }
  if (index < 0 || index >= static_cast<int>(items_.size())) {
    return;
  }
  currentIndex_ = index;
  emit currentIndexChanged(index);
  emit currentTextChanged(currentText());
  update();
  if (autoWidth_) {
    QTimer::singleShot(0, this, [this] { adjustWidthToContent(); });
  }
}

void ScrollableComboBox::updateState(int count, int currentIndex,
                                     const QString& text,
                                     const std::vector<QString>& itemTexts) {
  currentIndex_ = currentIndex;
  if (!text.isEmpty() && currentIndex >= 0 &&
      currentIndex < static_cast<int>(items_.size())) {
    items_[currentIndex_].text = text;
    items_[currentIndex_].normalizedText = normalizeForSearch(text);
  }
  if (!itemTexts.empty()) {
    items_.clear();
    items_.reserve(itemTexts.size());
    for (const auto& t : itemTexts) {
      items_.emplace_back(t, QVariant{});
    }
  }
  update();
  if (autoWidth_) {
    QTimer::singleShot(0, this, [this] { adjustWidthToContent(); });
  }
}

// ---------------------------------------------------------------------------
// item management
// ---------------------------------------------------------------------------

void ScrollableComboBox::addItem(const QString& text, const QVariant& data) {
  items_.emplace_back(text, data);
  if (currentIndex_ < 0) {
    currentIndex_ = 0;
  }
  update();
  if (autoWidth_) {
    QTimer::singleShot(0, this, [this] { adjustWidthToContent(); });
  }
}

void ScrollableComboBox::setItems(std::vector<ComboItem> items) {
  items_ = std::move(items);
  currentIndex_ = items_.empty() ? -1 : 0;
  emit currentIndexChanged(currentIndex_);
  emit currentTextChanged(currentText());
  update();
  if (autoWidth_) {
    QTimer::singleShot(0, this, [this] { adjustWidthToContent(); });
  }
}

void ScrollableComboBox::clear() {
  items_.clear();
  currentIndex_ = -1;
  update();
}

// ---------------------------------------------------------------------------
// search
// ---------------------------------------------------------------------------

void ScrollableComboBox::setSearchEnabled(bool enabled) {
  searchEnabled_ = enabled;
  overlay_->setSearchEnabled(enabled);
}

// ---------------------------------------------------------------------------
// sizing
// ---------------------------------------------------------------------------

QSize ScrollableComboBox::sizeHint() const {
  QFontMetrics fm(font());
  int width = 80;
  for (const auto& item : items_) {
    width = std::max(width, fm.horizontalAdvance(item.text) + 60);
  }
  return {width, kBaseHeight};
}

// ---------------------------------------------------------------------------
// paint
// ---------------------------------------------------------------------------

void ScrollableComboBox::paintEvent(QPaintEvent*) {
  const Palette& colors = Theme::palette();
  QPainter p(this);
  p.setRenderHint(QPainter::Antialiasing);

  // Background — mirror Python _ComboContentLayer approach:
  // Surface-variant background with theme-token border.
  const QColor inputBg = Theme::getColor(QStringLiteral("dialog.input.background"));
  const QColor borderColor = Theme::getColor(QStringLiteral("input.border.thin"));
  p.setPen(Qt::NoPen);
  p.setBrush(inputBg);
  p.drawRoundedRect(rect().adjusted(0, 0, -1, -1), kRadius, kRadius);
  p.setPen(QPen(borderColor, 1.0));
  p.setBrush(Qt::NoBrush);
  p.drawRoundedRect(QRectF(rect()).adjusted(0.5, 0.5, -0.5, -0.5), kRadius, kRadius);

  // Text — Python: rect.x()+12, rect.y(), max(0, rect.width()-12-28), rect.height().
  const QFont itemFont = getItemFont();
  p.setFont(itemFont);
  p.setPen(colors.text);
  const QRect textRect(kTextHPad, 0,
                       std::max(0, width() - kTextHPad - (kArrowRightMargin + 14)),
                       height());
  QFontMetrics fm(itemFont);
  const QString elided = fm.elidedText(currentText(), Qt::ElideRight,
                                       textRect.width());
  p.drawText(textRect, Qt::AlignVCenter | Qt::AlignLeft, elided);

  // Arrow — polyline matching Python: (cx-4, cy-1), (cx, cy+2), (cx+4, cy-1).
  p.setPen(QPen(colors.text, 1.5));
  const int cx = width() - kArrowRightMargin;
  const int cy = height() / 2;
  const QPoint poly[3] = {
      QPoint(cx - 4, cy - 1),
      QPoint(cx,     cy + 2),
      QPoint(cx + 4, cy - 1),
  };
  p.setBrush(Qt::NoBrush);
  p.drawPolyline(poly, 3);
}

// ---------------------------------------------------------------------------
// events
// ---------------------------------------------------------------------------

void ScrollableComboBox::mousePressEvent(QMouseEvent*) { openOverlay(); }

void ScrollableComboBox::applyDebouncedIndex() {
  if (pendingIndex_ != -1 && pendingIndex_ != currentIndex()) {
    emit wheelScrolledToIndex(pendingIndex_);
  }
  pendingIndex_ = -1;
}

void ScrollableComboBox::wheelEvent(QWheelEvent* event) {
  if (!isEnabled() || count() <= 1) {
    event->ignore();
    return;
  }
  const int startIndex = debounceTimer_->isActive()
                             ? pendingIndex_
                             : currentIndex();
  const int delta = event->angleDelta().y();
  int newIndex = startIndex;
  if (delta > 0) {
    newIndex = (startIndex - 1 + count()) % count();
  } else if (delta < 0) {
    newIndex = (startIndex + 1) % count();
  } else {
    return;
  }
  if (newIndex != startIndex) {
    pendingIndex_ = newIndex;
    // Display the pending text immediately (Python behaviour).
    if (newIndex >= 0 && newIndex < static_cast<int>(items_.size())) {
      items_[currentIndex_].text = items_[newIndex].text;
    }
    debounceTimer_->start();
    update();
    event->accept();
  }
}

void ScrollableComboBox::keyPressEvent(QKeyEvent* event) {
  if (event->key() == Qt::Key_Return || event->key() == Qt::Key_Enter ||
      event->key() == Qt::Key_Space) {
    openOverlay();
    return;
  }
  if (event->key() == Qt::Key_Down &&
      currentIndex_ + 1 < static_cast<int>(items_.size())) {
    setCurrentIndex(currentIndex_ + 1);
    return;
  }
  if (event->key() == Qt::Key_Up && currentIndex_ > 0) {
    setCurrentIndex(currentIndex_ - 1);
    return;
  }
  QWidget::keyPressEvent(event);
}

void ScrollableComboBox::changeEvent(QEvent* event) {
  if (event->type() == QEvent::FontChange ||
      event->type() == QEvent::ApplicationFontChange) {
    updateGeometry();
    if (autoWidth_) {
      QTimer::singleShot(0, this, [this] { adjustWidthToContent(); });
    }
  }
  QWidget::changeEvent(event);
}

// ---------------------------------------------------------------------------
// overlay
// ---------------------------------------------------------------------------

void ScrollableComboBox::openOverlay() {
  overlay_->setItems(items_);
  overlay_->showForAnchor(this);
}

void ScrollableComboBox::onOverlaySelection(int index) {
  setCurrentIndex(index);
}

}  // namespace sli::toolkit::comboboxes