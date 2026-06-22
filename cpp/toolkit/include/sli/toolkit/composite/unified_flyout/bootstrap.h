#pragma once

#include <QObject>

#include <memory>

#include "sli/toolkit/composite/unified_flyout/dragdrop.h"
#include "sli/toolkit/composite/unified_flyout/panel.h"
#include "sli/toolkit/composite/unified_flyout/refresh.h"
#include "sli/toolkit/composite/unified_flyout/session.h"

namespace sli::toolkit::unified_flyout {

// Bootstrap composes panel + session + (optional) refresh + dragdrop into one
// ready-to-use unit. Owns the lifecycle of its members.
class FlyoutBootstrap : public QObject {
  Q_OBJECT

 public:
  explicit FlyoutBootstrap(QWidget* parent = nullptr);

  Panel* panel() { return panel_; }
  Session* session() { return session_.get(); }

  void enableRefresh(RefreshPolicy::Producer producer);
  void enableDragDrop(DragDropPolicy::DropSink sink);

 private:
  Panel* panel_ = nullptr;
  std::unique_ptr<Session> session_;
  std::unique_ptr<RefreshPolicy> refresh_;
  std::unique_ptr<DragDropPolicy> dragdrop_;
};

}  // namespace sli::toolkit::unified_flyout
