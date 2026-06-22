#include "sli/toolkit/atomic/minimalist_scrollbar.h"

#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QEnterEvent>

#include <algorithm>

#include "sli/toolkit/theme.h"

namespace sli::toolkit {

MinimalistScrollBar::MinimalistScrollBar(Qt::Orientation orientation,
                                         QWidget* parent)
    : QScrollBar(orientation, parent) {
  setMouseTracking(true);
  updateColors();
  // Python: `self.theme_manager.theme_changed.connect(self._update_colors)`
  Theme::onThemeChanged(this, [this] { updateColors(); });
  registerHoverTracking();
}

void MinimalistScrollBar::registerHoverTracking() {
  // Python: `register_hover_widget(self)` from helpers.
  // This is typically done by a global hover manager, but we ensure
  // mouse tracking is on so enterEvent/leaveEvent are triggered.
  // No-op here as mouse tracking is already enabled in constructor.
}

bool MinimalistScrollBar::hoverHitTest(const QPoint& pos) const {
  // Python: `def hoverHitTest(self, pos) -> bool:`
  // Convert to point if needed and check if within rect.
  return rect().contains(pos);
}

void MinimalistScrollBar::setHoverActive(bool active) {
  // Python: `def setHoverActive(self, active: bool) -> None:`
  active = static_cast<bool>(active);  // Coerce to bool
  if (isHovered_ != active) {
    isHovered_ = active;
    update();
  }
}

void MinimalistScrollBar::updateColors() {
  // Python: `def _update_colors(self):`
  if (Theme::isDark()) {
    idleColor_ = QColor(255, 255, 255, 60);
    hoverColor_ = QColor(255, 255, 255, 90);
  } else {
    idleColor_ = QColor(0, 0, 0, 70);
    hoverColor_ = QColor(0, 0, 0, 100);
  }
  update();
}

void MinimalistScrollBar::paintEvent(QPaintEvent* event) {
  // Python: `def paintEvent(self, event):`
  if (minimum() == maximum()) {
    return;
  }
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);

  const QRect hRect = handleRect();
  if (hRect.isEmpty()) {
    return;
  }

  QColor currentColor;
  if (isDragging_) {
    // Python: `current_color = self.theme_manager.get_color("accent")`
    currentColor = Theme::getColor(QStringLiteral("accent"));
  } else if (isHovered_) {
    currentColor = hoverColor_;
  } else {
    currentColor = idleColor_;
  }

  painter.setPen(Qt::NoPen);
  painter.setBrush(currentColor);
  const double radius = std::min(hRect.width(), hRect.height()) / 2.0;
  painter.drawRoundedRect(hRect, radius, radius);
}

QRect MinimalistScrollBar::handleRect() const {
  // Python: `def _get_handle_rect(self):`
  if (minimum() == maximum()) {
    return QRect();
  }

  int currentThickness;
  if (isDragging_) {
    currentThickness = kDragThickness;
  } else if (isHovered_) {
    currentThickness = kHoverThickness;
  } else {
    currentThickness = kIdleThickness;
  }

  const double totalRange = static_cast<double>(maximum() - minimum() + pageStep());
  const double scrollRange = static_cast<double>(maximum() - minimum());

  if (totalRange <= 0.0) {
    return QRect();
  }

  if (orientation() == Qt::Vertical) {
    // Python Vertical branch
    const int grooveLen = height() - kPadding * 2;
    if (grooveLen <= 0) {
      return QRect();
    }

    double handleLen = (pageStep() / totalRange) * grooveLen;
    handleLen = std::max(handleLen, static_cast<double>(kMinHandleLength));

    const int trackLen = grooveLen - static_cast<int>(handleLen);
    double handlePosRel = 0.0;
    if (scrollRange > 0.0) {
      handlePosRel = ((value() - minimum()) / scrollRange) * trackLen;
    }

    const int handleY = static_cast<int>(handlePosRel) + kPadding;
    const int handleX = (width() - currentThickness) / 2;

    return QRect(handleX, handleY, currentThickness, static_cast<int>(handleLen));
  }

  // Python Horizontal branch
  const int grooveLen = width() - kPadding * 2;
  if (grooveLen <= 0) {
    return QRect();
  }

  double handleLen = (pageStep() / totalRange) * grooveLen;
  handleLen = std::max(handleLen, static_cast<double>(kMinHandleLength));

  const int trackLen = grooveLen - static_cast<int>(handleLen);
  double handlePosRel = 0.0;
  if (scrollRange > 0.0) {
    handlePosRel = ((value() - minimum()) / scrollRange) * trackLen;
  }

  const int handleX = static_cast<int>(handlePosRel) + kPadding;
  const int handleY = (height() - currentThickness) / 2;

  return QRect(handleX, handleY, static_cast<int>(handleLen), currentThickness);
}

void MinimalistScrollBar::enterEvent(QEnterEvent* event) {
  // Python: `def enterEvent(self, event):`
  setHoverActive(true);
  QScrollBar::enterEvent(event);
}

void MinimalistScrollBar::leaveEvent(QEvent* event) {
  // Python: `def leaveEvent(self, event):`
  setHoverActive(false);
  QScrollBar::leaveEvent(event);
}

void MinimalistScrollBar::mousePressEvent(QMouseEvent* event) {
  // Python: `def mousePressEvent(self, event):`
  if (event->button() != Qt::LeftButton) {
    return;
  }

  const QRect hRect = handleRect();
  const int posVal = (orientation() == Qt::Vertical) ? event->pos().y()
                                                       : event->pos().x();
  const int handleStart = (orientation() == Qt::Vertical) ? hRect.y() : hRect.x();

  if (hRect.contains(event->pos())) {
    isDragging_ = true;
    dragStartOffset_ = posVal - handleStart;
    update();
    event->accept();
    return;
  }

  // Click above/below (or left/right) handle — jump to position.
  const int handleLen = (orientation() == Qt::Vertical) ? hRect.height()
                                                         : hRect.width();
  const int trackLen =
      ((orientation() == Qt::Vertical) ? (height() - kPadding * 2)
                                       : (width() - kPadding * 2)) -
      handleLen;
  const double newPosClick = posVal - kPadding - (handleLen / 2.0);
  const double scrollRange = static_cast<double>(maximum() - minimum());

  if (trackLen > 0) {
    const int newValue = minimum() + static_cast<int>((newPosClick / trackLen) * scrollRange);
    setValue(newValue);
    isDragging_ = true;
    dragStartOffset_ = handleLen / 2;
    update();
  }

  event->accept();
}

void MinimalistScrollBar::mouseMoveEvent(QMouseEvent* event) {
  // Python: `def mouseMoveEvent(self, event):`
  if (!isDragging_) {
    event->accept();
    return;
  }

  const int padding = kPadding;
  int handleLen;
  int trackLen;
  int mousePos;

  if (orientation() == Qt::Vertical) {
    handleLen = handleRect().height();
    trackLen = (height() - padding * 2) - handleLen;
    mousePos = event->pos().y();
  } else {
    handleLen = handleRect().width();
    trackLen = (width() - padding * 2) - handleLen;
    mousePos = event->pos().x();
  }

  const double mousePosInTrack = mousePos - padding - dragStartOffset_;
  const double scrollRange = static_cast<double>(maximum() - minimum());

  if (trackLen > 0) {
    const int newValue = minimum() + static_cast<int>((mousePosInTrack / trackLen) * scrollRange);
    setValue(newValue);
  }

  event->accept();
}

void MinimalistScrollBar::mouseReleaseEvent(QMouseEvent* event) {
  // Python: `def mouseReleaseEvent(self, event):`
  if (event->button() == Qt::LeftButton) {
    isDragging_ = false;
    update();
    event->accept();
  }
}

}  // namespace sli::toolkit
