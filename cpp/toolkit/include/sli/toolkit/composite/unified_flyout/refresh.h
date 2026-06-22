#pragma once

#include <QObject>
#include <QTimer>

#include <functional>
#include <vector>

#include "sli/toolkit/composite/unified_flyout/model.h"

namespace sli::toolkit::unified_flyout {

class Panel;

// Refresh policy: schedule periodic or debounced reloads of the panel model
// from a producer callback.
class RefreshPolicy : public QObject {
  Q_OBJECT

 public:
  using Producer = std::function<std::vector<FlyoutItem>()>;

  explicit RefreshPolicy(Panel* panel, Producer producer,
                         QObject* parent = nullptr);

  void setDebounceMs(int ms);
  void requestReload();

 private slots:
  void doReload();

 private:
  Panel* panel_ = nullptr;
  Producer producer_;
  QTimer debounceTimer_;
};

}  // namespace sli::toolkit::unified_flyout
