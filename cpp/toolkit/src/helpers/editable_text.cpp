#include "sli/toolkit/helpers/editable_text.h"

#include <QApplication>
#include <QEvent>
#include <QKeyEvent>
#include <QLineEdit>
#include <QMouseEvent>
#include <QTimer>
#include <QWidget>

#include <memory>

namespace sli::toolkit {

namespace {

class EditableTextEventFilter : public QObject {
public:
    explicit EditableTextEventFilter(QWidget* widget)
        : QObject(widget)
        , widget_(widget)
    {
    }

    bool eventFilter(QObject* watched, QEvent* event) override
    {
        if (event->type() == QEvent::KeyPress && watched == widget_) {
            auto* keyEvent = static_cast<QKeyEvent*>(event);
            if (keyEvent->key() == Qt::Key_Return
                || keyEvent->key() == Qt::Key_Enter) {
                if (auto* lineEdit = qobject_cast<QLineEdit*>(widget_)) {
                    QTimer::singleShot(0, lineEdit, &QLineEdit::clearFocus);
                }
                return false;
            }
        }

        if (event->type() == QEvent::MouseButtonPress) {
            auto* widget = qobject_cast<QWidget*>(watched);
            if (widget && widget_ && widget != widget_
                && !widget_->isAncestorOf(widget)
                && widget_->hasFocus()) {
                QTimer::singleShot(0, widget_, &QWidget::clearFocus);
            }
        }

        return QObject::eventFilter(watched, event);
    }

private:
    QWidget* widget_;
};

} // anonymous namespace

void applyEditableTextBehavior(QWidget* widget)
{
    if (widget->property("_editable_text_behavior_installed").toBool())
        return;

    auto* filter = new EditableTextEventFilter(widget);
    widget->installEventFilter(filter);

    auto* app = QApplication::instance();
    if (app) {
        app->installEventFilter(filter);
        QObject::connect(widget, &QObject::destroyed, [app, filter]() {
            app->removeEventFilter(filter);
        });
    }

    widget->setProperty("_editable_text_behavior_installed", true);
}

}  // namespace sli::toolkit