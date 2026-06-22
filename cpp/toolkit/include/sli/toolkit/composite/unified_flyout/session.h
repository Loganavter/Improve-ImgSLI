#pragma once

#include <QObject>

class QWidget;

namespace sli::toolkit::unified_flyout {

class Panel;

// Session owns the open/close lifecycle of a Panel for a given anchor.
// It restores keyboard focus to the anchor on close and forwards selection
// signals as a typed `activated` event.
class Session : public QObject {
  Q_OBJECT

 public:
  explicit Session(Panel* panel, QObject* parent = nullptr);

  void open(QWidget* anchor);
  void close();

 signals:
  void activated(int index);
  void closed();

 private:
  Panel* panel_ = nullptr;
  QWidget* anchor_ = nullptr;
};

}  // namespace sli::toolkit::unified_flyout
