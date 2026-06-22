#include "sli/toolkit/overlays/in_window_overlay.h"

#include <QApplication>
#include <QEvent>
#include <QHBoxLayout>
#include <QHideEvent>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QResizeEvent>
#include <QWidget>

namespace sli::toolkit {

TopLevelInWindowOverlay::TopLevelInWindowOverlay(
    QWidget* parent,
    QWidget* anchor,
    bool closeOnBackground,
    bool closeOnEscape,
    bool closeOnDeactivate,
    int defaultDistance
)
    : QWidget(parent)
    , anchor_(anchor)
    , closeOnBackground_(closeOnBackground)
    , closeOnEscape_(closeOnEscape)
    , closeOnDeactivate_(closeOnDeactivate)
    , defaultDistance_(defaultDistance)
{
    if (parent == nullptr)
        qFatal("TopLevelInWindowOverlay requires an in-window parent widget");

    setWindowFlags(Qt::Widget);
    setAttribute(Qt::WA_NoSystemBackground, true);
    setAttribute(Qt::WA_TranslucentBackground, true);
    setFocusPolicy(Qt::StrongFocus);
    setMouseTracking(true);
    hide();
}

void TopLevelInWindowOverlay::setAnchor(QWidget* anchor) {
    anchor_ = anchor;
    if (isVisible())
        reposition();
}

QWidget* TopLevelInWindowOverlay::addWidget(
    QWidget* widget,
    const QString& key,
    std::optional<OverlaySlot> slot,
    std::optional<int> distance,
    std::optional<QRect> geometry
) {
    widget->setParent(this);
    OverlayItem item;
    item.key = key;
    item.widget = widget;
    item.slot = slot;
    item.distance = distance;
    item.geometry = geometry;
    items_.append(item);
    widget->show();
    if (isVisible())
        reposition();
    return widget;
}

void TopLevelInWindowOverlay::removeWidget(QWidget* widget) {
    items_.erase(
        std::remove_if(items_.begin(), items_.end(),
            [widget](const OverlayItem& item) { return item.widget == widget; }),
        items_.end()
    );
    widget->hide();
    widget->setParent(nullptr);
}

void TopLevelInWindowOverlay::clearWidgets(bool deleteWidgets) {
    QVector<OverlayItem> items = std::move(items_);
    items_.clear();
    for (const auto& item : items) {
        item.widget->hide();
        if (deleteWidgets) {
            item.widget->deleteLater();
        } else {
            item.widget->setParent(nullptr);
        }
    }
}

QWidget* TopLevelInWindowOverlay::widgetForKey(const QString& key) const {
    for (const auto& item : items_) {
        if (item.key == key)
            return item.widget;
    }
    return nullptr;
}

void TopLevelInWindowOverlay::showOverlay() {
    auto* parent = parentWidget();
    if (!parent)
        return;
    setGeometry(parent->rect());
    QWidget::show();
    raise();
    setFocus();
    reposition();
    installFilters();
}

void TopLevelInWindowOverlay::dismiss(bool emitSignal) {
    if (emitSignal)
        emit dismissed();
    hide();
}

// ---------------------------------------------------------------------------
// Protected event overrides
// ---------------------------------------------------------------------------

void TopLevelInWindowOverlay::hideEvent(QHideEvent* event) {
    removeFilters();
    QWidget::hideEvent(event);
}

void TopLevelInWindowOverlay::resizeEvent(QResizeEvent* event) {
    QWidget::resizeEvent(event);
    reposition();
}

void TopLevelInWindowOverlay::keyPressEvent(QKeyEvent* event) {
    if (closeOnEscape_ && event->key() == Qt::Key_Escape) {
        dismiss();
        event->accept();
        return;
    }
    QWidget::keyPressEvent(event);
}

void TopLevelInWindowOverlay::mousePressEvent(QMouseEvent* event) {
    if (closeOnBackground_) {
        dismiss();
        event->accept();
        return;
    }
    QWidget::mousePressEvent(event);
}

bool TopLevelInWindowOverlay::eventFilter(QObject* watched, QEvent* event) {
    const auto et = event->type();
    if (closeOnDeactivate_ &&
        (et == QEvent::WindowDeactivate || et == QEvent::ApplicationDeactivate))
    {
        dismiss();
        return false;
    }

    auto* parent = parentWidget();
    if (parent && watched == parent && et == QEvent::Resize) {
        setGeometry(parent->rect());
        reposition();
    }

    return QWidget::eventFilter(watched, event);
}

// ---------------------------------------------------------------------------
// Private helpers
// ---------------------------------------------------------------------------

void TopLevelInWindowOverlay::reposition() {
    const QPoint center = anchorCenter();
    for (auto& item : items_) {
        if (item.geometry.has_value()) {
            item.widget->setGeometry(item.geometry.value());
            continue;
        }

        const OverlaySlot slot = item.slot.value_or(OverlaySlot::CENTER);
        const int distance = item.distance.value_or(defaultDistance_);
        const QSize size = itemSize(item.widget);

        const auto [dx, dy] = overlaySlotVector(slot);
        const QPoint targetCenter(center.x() + dx * distance, center.y() + dy * distance);

        QRect rect(QPoint(0, 0), size);
        rect.moveCenter(targetCenter);
        item.widget->setGeometry(clampRect(rect));
    }
}

QSize TopLevelInWindowOverlay::itemSize(QWidget* widget) const {
    QSize size = widget->size();
    if (size.width() <= 0 || size.height() <= 0)
        size = widget->sizeHint();
    if (size.width() <= 0 || size.height() <= 0)
        size = QSize(1, 1);
    return size;
}

QPoint TopLevelInWindowOverlay::anchorCenter() const {
    if (anchor_ && anchor_->isVisible()) {
        const QPoint topLeft = mapFromGlobal(anchor_->mapToGlobal(QPoint(0, 0)));
        return QPoint(
            topLeft.x() + anchor_->width() / 2,
            topLeft.y() + anchor_->height() / 2
        );
    }
    return QPoint(width() / 2, height() / 2);
}

QRect TopLevelInWindowOverlay::clampRect(QRect rect) const {
    QRect result = rect;
    const QRect bounds = this->rect();
    if (result.width() > bounds.width())
        result.setWidth(bounds.width());
    if (result.height() > bounds.height())
        result.setHeight(bounds.height());
    if (result.right() > bounds.right())
        result.moveRight(bounds.right());
    if (result.left() < bounds.left())
        result.moveLeft(bounds.left());
    if (result.bottom() > bounds.bottom())
        result.moveBottom(bounds.bottom());
    if (result.top() < bounds.top())
        result.moveTop(bounds.top());
    return result;
}

void TopLevelInWindowOverlay::installFilters() {
    if (filtersInstalled_)
        return;

    auto* app = QApplication::instance();
    if (app)
        app->installEventFilter(this);

    filterParent_ = parentWidget();
    filterWindow_ = window();

    if (filterParent_)
        filterParent_->installEventFilter(this);
    if (filterWindow_ && filterWindow_ != filterParent_)
        filterWindow_->installEventFilter(this);

    filtersInstalled_ = true;
}

void TopLevelInWindowOverlay::removeFilters() {
    if (!filtersInstalled_)
        return;

    auto* app = QApplication::instance();
    if (app)
        app->removeEventFilter(this);
    if (filterParent_)
        filterParent_->removeEventFilter(this);
    if (filterWindow_ && filterWindow_ != filterParent_)
        filterWindow_->removeEventFilter(this);

    filterParent_ = nullptr;
    filterWindow_ = nullptr;
    filtersInstalled_ = false;
}

}  // namespace sli::toolkit