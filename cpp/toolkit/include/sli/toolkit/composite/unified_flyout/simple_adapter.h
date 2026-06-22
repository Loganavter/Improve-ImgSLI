#pragma once

#include <QString>
#include <QVariant>

#include <utility>
#include <vector>

#include "sli/toolkit/composite/unified_flyout/model.h"

namespace sli::toolkit::unified_flyout {

class Panel;

// Convenience adapter for simple text-only flyouts (no path/rating). Wraps
// `Panel::setItems` for the trivial case where each entry is just (label,
// data).
class SimpleAdapter {
 public:
  static void populate(Panel* panel,
                       const std::vector<std::pair<QString, QVariant>>& items);
};

}  // namespace sli::toolkit::unified_flyout
