#include "sli/toolkit/composite/unified_flyout/dragdrop.h"

#include <QDragEnterEvent>
#include <QDropEvent>
#include <QEvent>
#include <QMimeData>
#include <QStringList>
#include <QUrl>

#include "sli/toolkit/composite/unified_flyout/panel.h"

namespace sli::toolkit::unified_flyout {

DragDropPolicy::DragDropPolicy(Panel* panel, DropSink sink, QObject* parent)
    : QObject(parent), panel_(panel), sink_(std::move(sink)) {
  if (panel_ != nullptr) {
    panel_->setAcceptDrops(true);
    panel_->installEventFilter(this);
  }
}

bool DragDropPolicy::eventFilter(QObject* watched, QEvent* event) {
  if (watched != panel_) {
    return false;
  }
  if (event->type() == QEvent::DragEnter) {
    auto* dragEvent = static_cast<QDragEnterEvent*>(event);
    if (dragEvent->mimeData()->hasUrls()) {
      dragEvent->acceptProposedAction();
      return true;
    }
  } else if (event->type() == QEvent::Drop) {
    auto* dropEvent = static_cast<QDropEvent*>(event);
    QStringList paths;
    for (const QUrl& url : dropEvent->mimeData()->urls()) {
      if (url.isLocalFile()) {
        paths.append(url.toLocalFile());
      }
    }
    if (!paths.isEmpty() && sink_) {
      sink_(paths);
      dropEvent->acceptProposedAction();
      return true;
    }
  }
  return false;
}

}  // namespace sli::toolkit::unified_flyout
