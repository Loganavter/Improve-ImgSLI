#include "sli/toolkit/composite/unified_flyout/overlay_list_view.h"

#include <QKeyEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QResizeEvent>
#include <QScrollBar>

#include "sli/toolkit/composite/unified_flyout/minimalist_scrollbar.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::unified_flyout {

OverlayListView::OverlayListView(QWidget* parent) : QListView(parent) {
  setFrameShape(QFrame::NoFrame);
  setVerticalScrollMode(QAbstractItemView::ScrollPerPixel);
  setMouseTracking(true);
  setSelectionMode(QAbstractItemView::SingleSelection);
  setAttribute(Qt::WA_TranslucentBackground);

  // Python: `self.setVerticalScrollBarPolicy(ScrollBarAlwaysOff)` and
  // use MinimalistScrollBar for custom scrollbar.
  setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

  scrollbar_ = new MinimalistScrollBar(this);

  // Sync scrollbar ↔ native scroll bar.
  connect(verticalScrollBar(), &QScrollBar::valueChanged,
          scrollbar_, &QScrollBar::setValue);
  connect(scrollbar_, &QScrollBar::valueChanged,
          verticalScrollBar(), &QScrollBar::setValue);
  connect(verticalScrollBar(), &QScrollBar::rangeChanged,
          scrollbar_, &QScrollBar::setRange);
  connect(verticalScrollBar(), &QScrollBar::rangeChanged, this,
          [this]() { syncStepsFromNative(); });

  scrollbar_->setVisible(false);
  syncStepsFromNative();
  scrollbar_->installEventFilter(this);
}

void OverlayListView::keyPressEvent(QKeyEvent* event) {
  if (event->key() == Qt::Key_Escape) {
    emit escapePressed();
    return;
  }
  QListView::keyPressEvent(event);
}

void OverlayListView::paintEvent(QPaintEvent* event) {
  QPainter p(viewport());
  p.setPen(Qt::NoPen);
  p.setBrush(sli::toolkit::Theme::getColor(
      QStringLiteral("flyout.background")));
  p.drawRect(viewport()->rect());
  p.end();
  QListView::paintEvent(event);
}

void OverlayListView::resizeEvent(QResizeEvent* event) {
  QListView::resizeEvent(event);
  positionScrollbar();
  syncStepsFromNative();
  updateScrollbarVisibility();
}

void OverlayListView::syncStepsFromNative() {
  QScrollBar* native = verticalScrollBar();
  scrollbar_->blockSignals(true);
  scrollbar_->setPageStep(native->pageStep());
  scrollbar_->setSingleStep(native->singleStep());
  scrollbar_->blockSignals(false);
}

void OverlayListView::updateScrollbarVisibility() {
  QScrollBar* native = verticalScrollBar();
  const bool need = native->maximum() > 0;

  if (need) {
    setViewportMargins(0, 0, kScrollbarWidth + kScrollbarGap, 0);
    scrollbar_->setVisible(true);
  } else {
    setViewportMargins(0, 0, 0, 0);
    scrollbar_->setVisible(false);
  }
  positionScrollbar();
}

void OverlayListView::positionScrollbar() {
  const int x = width() - kScrollbarWidth;
  scrollbar_->setGeometry(x, 0, kScrollbarWidth, height());
  scrollbar_->raise();
}

bool OverlayListView::eventFilter(QObject* obj, QEvent* event) {
  // Python: passes mouse events on scrollbar rect through to the
  // custom scrollbar so drag + click-to-track work.
  if (obj == scrollbar_) {
    // Allow scrollbar events through.
    return QListView::eventFilter(obj, event);
  }
  return QListView::eventFilter(obj, event);
}

}  // namespace sli::toolkit::unified_flyout