#pragma once

#include <Qt>

class QWidget;
class QWheelEvent;

namespace sli::toolkit {

/// Shared wheel-scroll focus policy for custom scrollable widgets.
/// Mirrors Python `WheelScrollPolicyMixin` from `wheel_scroll_policy.py`.
///
/// Usage in a widget that wants this behavior:
///   - Store a `WheelScrollPolicy` member.
///   - Override wheelEvent, call `policy.handleWheelEvent(this, event)`.
class WheelScrollPolicy final {
public:
    explicit WheelScrollPolicy(bool wheelRequiresFocus = false);

    void setWheelRequiresFocus(bool required);
    bool wheelRequiresFocus() const;

    /// Returns true if the wheel event should be handled by the widget.
    /// If the widget does not have focus and wheel_requires_focus is set,
    /// calls event.ignore() and returns false.
    /// Otherwise attempts to set focus from the wheel event.
    bool shouldHandleWheelEvent(QWidget* widget, QWheelEvent* event);

private:
    bool wheelRequiresFocus_;

    void focusFromWheel(QWidget* widget);
};

}  // namespace sli::toolkit