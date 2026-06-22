#pragma once

#include <QObject>
#include <QTimer>

#include <utility>

#include "sli/toolkit/buttons/capabilities/capability.h"

class QWheelEvent;

namespace sli::toolkit::buttons {

class ButtonController;

class ScrollCapability : public QObject, public ButtonCapability {
  Q_OBJECT

 public:
  ScrollCapability(int minValue, int maxValue,
                   ButtonController* controller = nullptr,
                   QObject* parent = nullptr);

  void attach(QWidget* button,
              std::optional<QString> regionId = std::nullopt) override;
  void detach(QWidget* button) override;
  bool isEnabled() const override;

  bool handleWheelEvent(QWheelEvent* event);
  void setController(ButtonController* controller) { controller_ = controller; }

 signals:
  void scrollValueChanged(const QString& regionId, int value);
  void scrollStarted(const QString& regionId);
  void scrollEnded(const QString& regionId);

 private slots:
  void onScrollEnded();

 private:
  std::pair<int, int> range_;
  ButtonController* controller_ = nullptr;
  QTimer endTimer_;
};

}  // namespace sli::toolkit::buttons
