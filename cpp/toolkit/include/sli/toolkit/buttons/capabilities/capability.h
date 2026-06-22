#pragma once

#include <QString>

#include <optional>

class QWidget;

namespace sli::toolkit::buttons {

class ButtonCapability {
 public:
  virtual ~ButtonCapability() = default;

  virtual void attach(QWidget* button,
                      std::optional<QString> regionId = std::nullopt) {
    button_ = button;
    regionId_ = regionId.value_or(QStringLiteral("_main"));
  }

  virtual void detach(QWidget* button) {
    Q_UNUSED(button);
    button_ = nullptr;
  }

  virtual bool isEnabled() const { return button_ != nullptr; }

  QWidget* button() const { return button_; }
  const QString& regionId() const { return regionId_; }

 protected:
  QWidget* button_ = nullptr;
  QString regionId_ = QStringLiteral("_main");
};

}  // namespace sli::toolkit::buttons
