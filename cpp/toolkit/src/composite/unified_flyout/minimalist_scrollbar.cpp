#include "sli/toolkit/composite/unified_flyout/minimalist_scrollbar.h"

#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>

#include <algorithm>

#include "sli/toolkit/theme.h"

namespace sli::toolkit::unified_flyout {

MinimalistScrollBar::MinimalistScrollBar(QWidget* parent)
    : QScrollBar(Qt::Vertical, parent) {
  setMouseTracking(true);
  updateColors();
  // Python: `self.theme_manager.theme_changed.connect(self._update_colors)`
  sli::toolkit::Theme::onThemeChanged(this, [this] { updateColors(); });
}

void MinimalistScrollBar::updateColors() {
  if (sli::toolkit::Theme::isDark()) {
    idleColor_ = QColor(255, 255, 255, 60);
    hoverColor_ = QColor(255, 255, 255, 90);
  } else {
    idleColor_ = QColor(0, 0, 0, 70);
    hoverColor_ = QColor(0, 0, 0, 100);
  }
  update();
}

void MinimalistScrollBar::paintEvent(QPaintEvent*) {
  if (minimum() == maximum()) {
    return;
  }
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);

  const QRect hRect = handleRect();
  if (hRect.isEmpty()) {
    return;
  }

  QColor color;
  if (dragging_) {
    color = sli::toolkit::Theme::getColor(QStringLiteral("accent"));
  } else if (hovered_) {
    color = hoverColor_;
  } else {
    color = idleColor_;
  }

  painter.setPen(Qt::NoPen);
  painter.setBrush(color);
  const double radius = std::min(hRect.width(), hRect.height()) / 2.0;
  painter.drawRoundedRect(hRect, radius, radius);
}

QRect MinimalistScrollBar::handleRect() const {
  if (minimum() == maximum()) {
    return {};
  }

  int thickness;
  if (dragging_) {
    thickness = kDragThickness;
  } else if (hovered_) {
    thickness = kHoverThickness;
  } else {
    thickness = kIdleThickness;
  }

  const double totalRange =
      static_cast<double>(maximum() - minimum() + pageStep());
  const double scrollRange =
      static_cast<double>(maximum() - minimum());

  if (totalRange <= 0.0) {
    return {};
  }

  const int grooveLen = height() - kPadding * 2;
  if (grooveLen <= 0) {
    return {};
  }

  int handleLen = static_cast<int>(
      (pageStep() / totalRange) * grooveLen);
  handleLen = std::max(handleLen, kMinHandleLength);
  const int trackLen = grooveLen - handleLen;

  double handlePosRel = 0.0;
  if (scrollRange > 0.0) {
    handlePosRel =
        ((value() - minimum()) / scrollRange) * trackLen;
  }
  const int handleY = static_cast<int>(handlePosRel) + kPadding;
  const int handleX = (width() - thickness) / 2;

  return QRect(handleX, handleY, thickness, handleLen);
}

void MinimalistScrollBar::enterEvent(QEnterEvent* event) {
  hovered_ = true;
  update();
  QScrollBar::enterEvent(event);
}

void MinimalistScrollBar::leaveEvent(QEvent* event) {
  hovered_ = false;
  update();
  QScrollBar::leaveEvent(event);
}

void MinimalistScrollBar::mousePressEvent(QMouseEvent* event) {
  if (event->button() != Qt::LeftButton) {
    return;
  }
  const QRect hRect = handleRect();
  const int posVal = event->pos().y();
  const int handleStart = hRect.y();

  if (hRect.contains(event->pos())) {
    dragging_ = true;
    dragStartOffset_ = posVal - handleStart;
    update();
    event->accept();
    return;
  }

  // Click above/below handle — jump to position.
  const int handleLen = hRect.height();
  const int trackLen = (height() - kPadding * 2 - handleLen);
  const double newPosClick = posVal - kPadding - (handleLen / 2.0);
  const double sRange = static_cast<double>(maximum() - minimum());
  if (trackLen > 0) {
    const int newValue =
        minimum() + static_cast<int>((newPosClick / trackLen) * sRange);
    setValue(newValue);
    dragging_ = true;
    dragStartOffset_ = handleLen / 2;
    update();
  }
  event->accept();
}

void MinimalistScrollBar::mouseMoveEvent(QMouseEvent* event) {
  if (!dragging_) {
    return;
  }
  const int handleLen = handleRect().height();
  const int trackLen = (height() - kPadding * 2) - handleLen;
  const int mousePos = event->pos().y();
  const double mousePosInTrack = mousePos - kPadding - dragStartOffset_;
  const double sRange = static_cast<double>(maximum() - minimum());
  if (trackLen > 0) {
    const int newValue =
        minimum() + static_cast<int>((mousePosInTrack / trackLen) * sRange);
    setValue(newValue);
  }
  event->accept();
}

void MinimalistScrollBar::mouseReleaseEvent(QMouseEvent* event) {
  if (event->button() == Qt::LeftButton) {
    dragging_ = false;
    update();
    event->accept();
  }
}

}  // namespace sli::toolkit::unified_flyout