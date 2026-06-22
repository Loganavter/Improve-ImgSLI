#include "sli/toolkit/comboboxes/models.h"

#include "sli/toolkit/comboboxes/search.h"

namespace sli::toolkit::comboboxes {

ComboItem::ComboItem(QString t, QVariant d)
    : text(std::move(t)),
      data(std::move(d)),
      normalizedText(normalizeForSearch(text)) {}

}  // namespace sli::toolkit::comboboxes
