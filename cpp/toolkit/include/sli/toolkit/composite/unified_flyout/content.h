#pragma once

#include <vector>

#include "sli/toolkit/composite/unified_flyout/model.h"

namespace sli::toolkit::unified_flyout {

class Panel;

// Content adapter: populate a Panel from a typed item list.
// In Python this corresponds to `_UnifiedFlyoutContentMixin.populate(...)`.
class ContentAdapter {
 public:
  static void populate(Panel* panel, std::vector<FlyoutItem> items,
                       int currentIndex = -1);
};

}  // namespace sli::toolkit::unified_flyout
