#include "sli/toolkit/composite/unified_flyout/bootstrap.h"

namespace sli::toolkit::unified_flyout {

FlyoutBootstrap::FlyoutBootstrap(QWidget* parent) : QObject(parent) {
  panel_ = new Panel(parent);
  session_ = std::make_unique<Session>(panel_, this);
}

void FlyoutBootstrap::enableRefresh(RefreshPolicy::Producer producer) {
  refresh_ = std::make_unique<RefreshPolicy>(panel_, std::move(producer), this);
}

void FlyoutBootstrap::enableDragDrop(DragDropPolicy::DropSink sink) {
  dragdrop_ = std::make_unique<DragDropPolicy>(panel_, std::move(sink), this);
}

}  // namespace sli::toolkit::unified_flyout
