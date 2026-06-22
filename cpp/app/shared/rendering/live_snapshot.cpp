#include "shared/rendering/live_snapshot.h"

namespace imgsli::app::shared::rendering {

QString pathAtIndex(const QStringList& items, int index) {
  if (index < 0 || index >= items.size()) {
    return {};
  }
  return items.at(index);
}

}  // namespace imgsli::app::shared::rendering
