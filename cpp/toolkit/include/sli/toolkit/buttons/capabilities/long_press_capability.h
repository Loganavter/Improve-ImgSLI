#pragma once

#include <QObject>
#include <QTimer>

#include "sli/toolkit/buttons/capabilities/capability.h"

namespace sli::toolkit::buttons {

class LongPressCapability : public QObject, public ButtonCapability {
  Q_OBJECT

 public:
  explicit LongPressCapability(int delayMs = 600, QObject* parent = nullptr);

  void attach(QWidget* button,
              std::optional<QString> regionId = std::nullopt) override;
  void detach(QWidget* button) override;
  bool isEnabled() const override;

  void onPressStart();
  void onPressEnd();
  bool wasLongPressed() const { return triggered_; }

 signals:
  void longPressed(const QString& regionId);

 private slots:
  void onTimeout();

 private:
  int delayMs_;
  QTimer timer_;
  bool triggered_ = false;
};

}  // namespace sli::toolkit::buttons
