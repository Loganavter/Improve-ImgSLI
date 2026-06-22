#pragma once

#include <QObject>
#include <QPoint>

#include <functional>
#include <vector>

class QEvent;
class QWidget;

namespace sli::toolkit {

/// Keeps custom-painted hover state consistent across related widgets.
/// Mirrors Python `HoverCoordinator` from `hover_coordinator.py`.
class HoverCoordinator : public QObject {
    Q_OBJECT

public:
    explicit HoverCoordinator(QObject* parent = nullptr);

    void registerWidget(QWidget* widget);
    void unregisterWidget(QWidget* widget);

    void reconcile(std::optional<QPoint> globalPos = std::nullopt,
                   QWidget* sourceWindow = nullptr);
    void clearAll();
    void clearDescendants(QWidget* root);

protected:
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    struct WidgetEntry {
        QWidget* widget;
        bool destroyed = false;
    };
    std::vector<WidgetEntry> widgets_;
    QObject* installedApp_ = nullptr;

    void removeDestroyed();
    void install();
    void reconcileWidget(QWidget* widget, const QPoint& globalPos);
    static bool isReconcilable(QWidget* widget);
    static void setHover(QWidget* widget, bool active);
    static std::optional<QPoint> globalPosFromEvent(QEvent* event);
};

// Singleton accessors — mirror Python module-level functions.
HoverCoordinator& hoverCoordinator();
void registerHoverWidget(QWidget* widget);
void unregisterHoverWidget(QWidget* widget);

}  // namespace sli::toolkit