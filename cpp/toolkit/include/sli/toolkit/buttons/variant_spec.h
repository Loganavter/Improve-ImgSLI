#pragma once

#include <QColor>
#include <QString>

#include <functional>

#include "sli/toolkit/buttons/state.h"

namespace sli::toolkit {
class Theme;
}

namespace sli::toolkit::buttons {

using BackgroundResolver =
    std::function<QColor(StateSet states, const Theme& theme)>;

struct VariantSpec {
  QString name;
  QString tokenPrefix;
  BackgroundResolver resolveBg;
};

}  // namespace sli::toolkit::buttons
