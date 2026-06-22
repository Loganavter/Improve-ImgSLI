#pragma once

class QWidget;

namespace sli::toolkit {

/// Install event-filter to make Return/Enter clear focus on a QLineEdit,
/// and clicking outside the widget also clears focus.
/// Mirrors Python `apply_editable_text_behavior()` from `editable_text.py`.
void applyEditableTextBehavior(QWidget* widget);

}  // namespace sli::toolkit