#pragma once

#include <QObject>
#include <QString>
#include <QVariant>

#include <utility>
#include <vector>

#include "sli/toolkit/buttons/capabilities/capability.h"

namespace sli::toolkit::buttons {

class DropdownMenu;

class MenuCapability : public QObject, public ButtonCapability {
  Q_OBJECT

 public:
  using MenuItem = std::pair<QString, QVariant>;

  explicit MenuCapability(std::vector<MenuItem> items = {},
                          QObject* parent = nullptr);
  ~MenuCapability() override;

  void attach(QWidget* button,
              std::optional<QString> regionId = std::nullopt) override;
  void detach(QWidget* button) override;
  bool isEnabled() const override;

  void setMenuItems(std::vector<MenuItem> items);
  void showMenu();

 signals:
  void menuTriggered(const QString& regionId, const QVariant& data);

 private:
  void initMenu();

  std::vector<MenuItem> items_;
  DropdownMenu* menuWidget_ = nullptr;
};

}  // namespace sli::toolkit::buttons
