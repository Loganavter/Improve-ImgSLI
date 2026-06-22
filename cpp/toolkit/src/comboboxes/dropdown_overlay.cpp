#include "sli/toolkit/comboboxes/dropdown_overlay.h"

#include <QApplication>
#include <QMouseEvent>
#include <QPainter>
#include <QPainterPath>
#include <QPen>
#include <QPoint>
#include <QRectF>
#include <QWheelEvent>

#include "sli/toolkit/atomic/minimalist_scrollbar.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "sli/toolkit/helpers/overlay_geometry.h"
#include "sli/toolkit/helpers/shadow_painter.h"
#include "sli/toolkit/theme.h"

namespace sli::toolkit::comboboxes {

// -------------------------------------------------------------------------
// DropdownItemSlot — reusable Button-based row slot
// -------------------------------------------------------------------------

class DropdownItemSlot : public sli::toolkit::Button {
  Q_OBJECT

 public:
  explicit DropdownItemSlot(int textPadding, QWidget* parent)
      : sli::toolkit::Button(
            [&]() -> sli::toolkit::Button::Config {
                sli::toolkit::Button::Config cfg;
                cfg.size = QSize(0, 0);
                cfg.cornerRadius = 6;
                cfg.deferClick = true;
                return cfg;
            }(),
            parent),
        textPadding_(textPadding),
        text_(),
        itemIndex_(-1) {
    // Wire deferred click to our signal.
    connect(this, &sli::toolkit::Button::regionClicked, this,
            [this](const QString&) { emit slotClicked(this); });
  }

  void bind(const QString& text, int itemIndex) {
    text_ = text;
    itemIndex_ = itemIndex;
    update();
  }

  int itemIndex() const { return itemIndex_; }

 signals:
  void slotClicked(DropdownItemSlot* self);

 protected:
  void paintEvent(QPaintEvent* /*event*/) override {
    // _SlotBgLayer + _SlotContentLayer
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    const bool hovered = underMouse();
    const bool pressed = isDown();
    if (hovered || pressed) {
        const QRect bgRect = rect().adjusted(0, 1, 0, -1);
        painter.setPen(Qt::NoPen);
        painter.setBrush(
            Theme::getColor(QStringLiteral("list_item.background.hover")));
        painter.drawRoundedRect(bgRect, 6, 6);
    }

    if (!text_.isEmpty()) {
        const QRect textRect = rect().adjusted(textPadding_, 0, -textPadding_, 0);
        painter.setPen(QPen(Theme::getColor(QStringLiteral("dialog.text"))));
        painter.setFont(font());
        QFontMetrics fm(font());
        const QString elided =
            fm.elidedText(text_, Qt::ElideRight, textRect.width());
        painter.drawText(textRect, Qt::AlignLeft | Qt::AlignVCenter, elided);
    }
  }

 private:
  int textPadding_;
  QString text_;
  int itemIndex_;
};

// -------------------------------------------------------------------------
// DropdownOverlay
// -------------------------------------------------------------------------

DropdownOverlay::DropdownOverlay(sli::toolkit::ComboBox* owner, QWidget* parent)
    : QWidget(parent),
      owner_(owner),
      slots_(),
      scrollbar_(new sli::toolkit::MinimalistScrollBar(Qt::Vertical, this)) {
    setWindowFlags(Qt::Widget);
    setAttribute(Qt::WA_StyledBackground, false);
    setMouseTracking(true);

    scrollbar_->setVisible(false);
    connect(scrollbar_, &QScrollBar::valueChanged, this,
            [this](int value) { onScrollbarValueChanged(value); });

    hide();
}

DropdownOverlay::~DropdownOverlay() = default;

// -------------------------------------------------------------------------
// geometry helpers
// -------------------------------------------------------------------------

int DropdownOverlay::itemHeight() const {
    return owner_->itemHeight();
}

int DropdownOverlay::visibleCount() const {
    return owner_->visibleItemCount();
}

int DropdownOverlay::listHeight() const {
    return visibleCount() * itemHeight();
}

QRect DropdownOverlay::contentRect() const {
    return rect().adjusted(kShadow, kShadow, -kShadow, -kShadow);
}

bool DropdownOverlay::hasScrollbar() const {
    return static_cast<int>(owner_->visibleIndices().size()) >
           owner_->maxVisibleItems();
}

QRect DropdownOverlay::listRect() const {
    int w = contentRect().width();
    if (hasScrollbar()) {
        w -= kScrollbarWidth;
    }
    return QRect(0, 0, std::max(0, w), listHeight());
}

QRect DropdownOverlay::itemRect(int visibleIndex) const {
    const QRect lr = listRect();
    return QRect(lr.x(),
                 lr.y() + visibleIndex * itemHeight(),
                 lr.width(),
                 itemHeight());
}

// -------------------------------------------------------------------------
// slot pool management
// -------------------------------------------------------------------------

void DropdownOverlay::ensureSlots(int count) {
    while (static_cast<int>(slots_.size()) < count) {
        auto* slot = new DropdownItemSlot(
            sli::toolkit::ComboBox::kTextHorizontalPadding, this);
        connect(slot, &DropdownItemSlot::slotClicked, this,
                [this](DropdownItemSlot* s) { onSlotClicked(s); });
        slots_.push_back(slot);
    }
    for (int i = count; i < static_cast<int>(slots_.size()); ++i) {
        slots_[i]->hide();
    }
}

void DropdownOverlay::rebindSlots() {
    const int visCount = visibleCount();
    const std::vector<int> visIdx = owner_->visibleIndices();
    ensureSlots(visCount);
    const QPoint contentTopLeft = contentRect().topLeft();
    for (int vi = 0; vi < visCount; ++vi) {
        const int sourcePos = owner_->scrollOffset() + vi;
        if (sourcePos >= static_cast<int>(visIdx.size())) {
            break;
        }
        const int itemIndex = visIdx[sourcePos];
        const auto& item = owner_->internalItems()[itemIndex];
        DropdownItemSlot* slot = slots_[vi];
        slot->bind(item.text, itemIndex);
        const QRect geom = itemRect(vi).translated(contentTopLeft);
        slot->setGeometry(geom);
        slot->show();
    }
    // Hide unused slots.
    for (int i = visCount; i < static_cast<int>(slots_.size()); ++i) {
        slots_[i]->hide();
    }
}

void DropdownOverlay::onSlotClicked(DropdownItemSlot* slot) {
    const int idx = slot->itemIndex();
    if (idx >= 0) {
        owner_->setCurrentIndex(idx);
    }
    owner_->hideDropdown();
}

// -------------------------------------------------------------------------
// show / position
// -------------------------------------------------------------------------

void DropdownOverlay::showForOwner() {
    owner_->ensureCurrentVisible();
    reposition();
    syncScrollbar();
    rebindSlots();
    show();
    raise();
    update();
}

void DropdownOverlay::reposition() {
    QWidget* win = parentWidget();
    if (!win) {
        return;
    }

    const int visCount = static_cast<int>(owner_->visibleIndices().size());
    const int visPos = std::max(
        0,
        owner_->visiblePositionForIndex(owner_->currentIndex()) -
            owner_->scrollOffset());

    const QRect outer = sli::toolkit::calculateCenteredOverlayGeometry(
        *owner_,
        *win,
        QSize(std::max(owner_->width(), owner_->minimumWidth()),
              listHeight()),
        kShadow,
        owner_->currentIndex(),
        visPos,
        itemHeight(),
        visCount > owner_->maxVisibleItems());

    setGeometry(outer);
    positionScrollbar();
}

void DropdownOverlay::positionScrollbar() {
    if (!hasScrollbar()) {
        scrollbar_->setVisible(false);
        return;
    }
    const QRect content = contentRect();
    const int x = content.right() - kScrollbarWidth + 1;
    scrollbar_->setGeometry(x, content.y(), kScrollbarWidth, content.height());
    scrollbar_->raise();
}

void DropdownOverlay::syncScrollbar() {
    const int totalVisible =
        static_cast<int>(owner_->visibleIndices().size());
    const int maxOffset = std::max(0, totalVisible - visibleCount());
    if (maxOffset <= 0) {
        scrollbar_->setVisible(false);
        return;
    }
    QSignalBlocker blocker(scrollbar_);
    scrollbar_->setRange(0, maxOffset);
    scrollbar_->setPageStep(visibleCount());
    scrollbar_->setSingleStep(1);
    scrollbar_->setValue(owner_->scrollOffset());
    scrollbar_->setVisible(true);
    positionScrollbar();
}

void DropdownOverlay::onScrollbarValueChanged(int value) {
    const int totalVisible =
        static_cast<int>(owner_->visibleIndices().size());
    const int newOffset = std::max(
        0, std::min(value, std::max(0, totalVisible - visibleCount())));
    if (newOffset == owner_->scrollOffset()) {
        return;
    }
    owner_->setScrollOffset(newOffset);
    rebindSlots();
    QWidget::update();
}

// -------------------------------------------------------------------------
// events
// -------------------------------------------------------------------------

void DropdownOverlay::paintEvent(QPaintEvent* /*event*/) {
    QPainter painter(this);
    painter.setRenderHint(QPainter::Antialiasing);

    const QRectF content = QRectF(contentRect());

    // Shadow
    sli::toolkit::drawRoundedShadow(painter, content, kShadow, kRadius);

    // Background + border (flyout.background / flyout.border)
    const QColor bg = Theme::getColor(QStringLiteral("flyout.background"));
    const QColor border = Theme::getColor(QStringLiteral("flyout.border"));

    QPainterPath path;
    path.addRoundedRect(content.adjusted(0.5, 0.5, -0.5, -0.5), kRadius, kRadius);
    painter.setPen(QPen(border, 1.0));
    painter.setBrush(QBrush(bg));
    painter.drawPath(path);
    // Slot widgets paint themselves (child Buttons).
}

void DropdownOverlay::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    positionScrollbar();
    syncScrollbar();
}

// ---- scrollbar pass-through ----

bool DropdownOverlay::forwardToScrollbar(QMouseEvent* event) {
    if (!scrollbar_->isVisible() ||
        !scrollbar_->geometry().contains(event->position().toPoint())) {
        return false;
    }
    const QPoint sbPos =
        scrollbar_->mapFromGlobal(event->globalPosition().toPoint());
    QApplication::sendEvent(
        scrollbar_,
        new QMouseEvent(event->type(), QPointF(sbPos),
                        event->globalPosition(), event->button(),
                        event->buttons(), event->modifiers()));
    event->accept();
    return true;
}

void DropdownOverlay::mousePressEvent(QMouseEvent* event) {
    if (event->button() == Qt::LeftButton && forwardToScrollbar(event)) {
        return;
    }
    QWidget::mousePressEvent(event);
}

void DropdownOverlay::mouseMoveEvent(QMouseEvent* event) {
    if (forwardToScrollbar(event)) {
        return;
    }
    QWidget::mouseMoveEvent(event);
}

void DropdownOverlay::mouseReleaseEvent(QMouseEvent* event) {
    if (event->button() == Qt::LeftButton && forwardToScrollbar(event)) {
        return;
    }
    QWidget::mouseReleaseEvent(event);
}

void DropdownOverlay::wheelEvent(QWheelEvent* event) {
    const int totalVisible =
        static_cast<int>(owner_->visibleIndices().size());
    if (totalVisible <= owner_->maxVisibleItems()) {
        event->ignore();
        return;
    }
    const int delta = event->angleDelta().y();
    if (delta > 0) {
        owner_->setScrollOffset(std::max(0, owner_->scrollOffset() - 1));
    } else if (delta < 0) {
        owner_->setScrollOffset(
            std::min(totalVisible - owner_->maxVisibleItems(),
                     owner_->scrollOffset() + 1));
    }
    syncScrollbar();
    rebindSlots();
    QWidget::update();
    event->accept();
}

}  // namespace sli::toolkit::comboboxes

#include "dropdown_overlay.moc"
