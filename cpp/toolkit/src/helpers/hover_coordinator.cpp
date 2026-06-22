#include "sli/toolkit/helpers/hover_coordinator.h"

#include <QApplication>
#include <QCursor>
#include <QEvent>
#include <QMouseEvent>
#include <QPointF>
#include <QWidget>

#include <algorithm>

namespace sli::toolkit {

HoverCoordinator::HoverCoordinator(QObject* parent)
    : QObject(parent)
{
}

void HoverCoordinator::registerWidget(QWidget* widget)
{
    install();
    // Remove any existing entry for this widget
    widgets_.erase(
        std::remove_if(widgets_.begin(), widgets_.end(),
                       [widget](const WidgetEntry& e) { return e.widget == widget; }),
        widgets_.end());
    widgets_.push_back({widget, false});
    widget->setMouseTracking(true);
    widget->setAttribute(Qt::WA_Hover, true);
    connect(widget, &QObject::destroyed, this, [this, widget]() {
        for (auto& e : widgets_) {
            if (e.widget == widget) {
                e.destroyed = true;
                break;
            }
        }
    });
}

void HoverCoordinator::unregisterWidget(QWidget* widget)
{
    widgets_.erase(
        std::remove_if(widgets_.begin(), widgets_.end(),
                       [widget](const WidgetEntry& e) { return e.widget == widget; }),
        widgets_.end());
}

void HoverCoordinator::reconcile(std::optional<QPoint> globalPos,
                                  QWidget* sourceWindow)
{
    removeDestroyed();
    QPoint pos = globalPos.value_or(QCursor::pos());
    for (auto& entry : widgets_) {
        if (sourceWindow && entry.widget->window() != sourceWindow) {
            setHover(entry.widget, false);
            continue;
        }
        reconcileWidget(entry.widget, pos);
    }
}

void HoverCoordinator::clearAll()
{
    removeDestroyed();
    for (auto& entry : widgets_) {
        setHover(entry.widget, false);
    }
}

void HoverCoordinator::clearDescendants(QWidget* root)
{
    removeDestroyed();
    for (auto& entry : widgets_) {
        if (entry.widget == root || root->isAncestorOf(entry.widget)) {
            setHover(entry.widget, false);
        }
    }
}

bool HoverCoordinator::eventFilter(QObject* watched, QEvent* event)
{
    switch (event->type()) {
    case QEvent::HoverEnter:
    case QEvent::HoverMove:
    case QEvent::Enter:
    case QEvent::MouseMove: {
        QWidget* sourceWindow = nullptr;
        if (auto* w = qobject_cast<QWidget*>(watched))
            sourceWindow = w->window();
        reconcile(globalPosFromEvent(event), sourceWindow);
        break;
    }
    case QEvent::Leave:
    case QEvent::Hide:
    case QEvent::WindowDeactivate:
    case QEvent::EnabledChange:
        if (auto* w = qobject_cast<QWidget*>(watched))
            clearDescendants(w);
        else
            clearAll();
        break;
    case QEvent::ApplicationDeactivate:
        clearAll();
        break;
    default:
        break;
    }
    return false;
}

void HoverCoordinator::removeDestroyed()
{
    widgets_.erase(
        std::remove_if(widgets_.begin(), widgets_.end(),
                       [](const WidgetEntry& e) { return e.destroyed; }),
        widgets_.end());
}

void HoverCoordinator::install()
{
    auto* app = QApplication::instance();
    if (!app || app == installedApp_)
        return;
    if (installedApp_)
        installedApp_->removeEventFilter(this);
    app->installEventFilter(this);
    installedApp_ = app;
}

void HoverCoordinator::reconcileWidget(QWidget* widget, const QPoint& globalPos)
{
    if (!isReconcilable(widget)) {
        setHover(widget, false);
        return;
    }

    QPoint local = widget->mapFromGlobal(globalPos);
    bool active = QRect(QPoint(0, 0), widget->size()).contains(local);

    if (active) {
        QWidget* topWidget = QApplication::widgetAt(globalPos);
        if (!topWidget
            || (topWidget != widget && !widget->isAncestorOf(topWidget))) {
            active = false;
        }
    }

    if (active) {
        // Check custom hoverHitTest if the widget supports it
        auto meta = widget->metaObject();
        if (meta) {
            int idx = meta->indexOfMethod("hoverHitTest(QPointF)");
            if (idx >= 0) {
                bool result = false;
                widget->metaObject()->invokeMethod(
                    widget, "hoverHitTest", Qt::DirectConnection,
                    Q_RETURN_ARG(bool, result),
                    Q_ARG(QPointF, QPointF(local)));
                active = result;
            }
        }
    }

    setHover(widget, active);
}

bool HoverCoordinator::isReconcilable(QWidget* widget)
{
    return widget->isVisible() && widget->isEnabled();
}

void HoverCoordinator::setHover(QWidget* widget, bool active)
{
    auto meta = widget->metaObject();
    if (meta && meta->indexOfMethod("setHoverActive(bool)") >= 0) {
        widget->metaObject()->invokeMethod(
            widget, "setHoverActive", Qt::DirectConnection,
            Q_ARG(bool, active));
    }
}

std::optional<QPoint> HoverCoordinator::globalPosFromEvent(QEvent* event)
{
    if (auto* me = dynamic_cast<QMouseEvent*>(event))
        return me->globalPosition().toPoint();
    return QCursor::pos();
}

// Singleton
namespace {
HoverCoordinator* g_coordinator = nullptr;
}

HoverCoordinator& hoverCoordinator()
{
    if (!g_coordinator)
        g_coordinator = new HoverCoordinator();
    return *g_coordinator;
}

void registerHoverWidget(QWidget* widget)
{
    hoverCoordinator().registerWidget(widget);
}

void unregisterHoverWidget(QWidget* widget)
{
    hoverCoordinator().unregisterWidget(widget);
}

}  // namespace sli::toolkit