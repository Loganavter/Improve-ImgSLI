#include "sli/toolkit/helpers/wheel_scroll_policy.h"

#include <QWheelEvent>
#include <QWidget>

namespace sli::toolkit {

WheelScrollPolicy::WheelScrollPolicy(bool wheelRequiresFocus)
    : wheelRequiresFocus_(wheelRequiresFocus)
{
}

void WheelScrollPolicy::setWheelRequiresFocus(bool required)
{
    wheelRequiresFocus_ = required;
}

bool WheelScrollPolicy::wheelRequiresFocus() const
{
    return wheelRequiresFocus_;
}

bool WheelScrollPolicy::shouldHandleWheelEvent(QWidget* widget, QWheelEvent* event)
{
    if (wheelRequiresFocus_ && !widget->hasFocus()) {
        event->ignore();
        return false;
    }
    if (!wheelRequiresFocus_) {
        focusFromWheel(widget);
    }
    return true;
}

void WheelScrollPolicy::focusFromWheel(QWidget* widget)
{
    if (widget->hasFocus())
        return;
    if (!widget->isEnabled() || widget->focusPolicy() == Qt::NoFocus)
        return;
    widget->setFocus(Qt::MouseFocusReason);
}

}  // namespace sli::toolkit