#pragma once

#include <QObject>
#include <QStringList>

class QDragEnterEvent;
class QDropEvent;
class QWidget;

namespace sli::toolkit::unified_flyout {

class Panel;

// Drag-and-drop policy: accept file URLs and forward them to a sink callback.
// Default accepts any non-empty MIME url list; subclasses can override mime
// filtering.
class DragDropPolicy : public QObject {
  Q_OBJECT

 public:
  using DropSink = std::function<void(const QStringList& paths)>;

  DragDropPolicy(Panel* panel, DropSink sink, QObject* parent = nullptr);

  bool eventFilter(QObject* watched, QEvent* event) override;

 private:
  Panel* panel_ = nullptr;
  DropSink sink_;
};

}  // namespace sli::toolkit::unified_flyout
