#include "sli/toolkit/composite/unified_flyout/session.h"

#include <QWidget>

#include "sli/toolkit/composite/unified_flyout/panel.h"

namespace sli::toolkit::unified_flyout {

Session::Session(Panel* panel, QObject* parent)
    : QObject(parent), panel_(panel) {
  if (panel_ != nullptr) {
    connect(panel_, &Panel::itemActivated, this, &Session::activated);
    connect(panel_, &Panel::closed, this, [this]() {
      if (anchor_ != nullptr) {
        anchor_->setFocus(Qt::OtherFocusReason);
      }
      emit closed();
    });
  }
}

void Session::open(QWidget* anchor) {
  anchor_ = anchor;
  if (panel_ != nullptr) {
    panel_->showForAnchor(anchor);
  }
}

void Session::close() {
  if (panel_ != nullptr) {
    panel_->close();
  }
}

}  // namespace sli::toolkit::unified_flyout
