#pragma once

#include <QFlags>

namespace sli::toolkit::buttons {

enum class ButtonState : unsigned int {
  None = 0,
  Hovered = 1U << 0,
  Pressed = 1U << 1,
  Checked = 1U << 2,
  Disabled = 1U << 3,
  Scrolling = 1U << 4,
  Focused = 1U << 5,
};

Q_DECLARE_FLAGS(StateSet, ButtonState)

}  // namespace sli::toolkit::buttons

Q_DECLARE_OPERATORS_FOR_FLAGS(sli::toolkit::buttons::StateSet)
