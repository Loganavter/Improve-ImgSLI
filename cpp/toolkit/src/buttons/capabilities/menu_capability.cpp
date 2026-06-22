#include "sli/toolkit/buttons/capabilities/menu_capability.h"

#include <QWidget>

#include "sli/toolkit/buttons/dropdown_menu.h"

namespace sli::toolkit::buttons {

MenuCapability::MenuCapability(std::vector<MenuItem> items, QObject* parent)
    : QObject(parent), items_(std::move(items)) {}

MenuCapability::~MenuCapability() {
  if (menuWidget_ != nullptr) {
    menuWidget_->deleteLater();
  }
}

void MenuCapability::attach(QWidget* button,
                            std::optional<QString> regionId) {
  ButtonCapability::attach(button, regionId);
  setParent(button);
  initMenu();
}

void MenuCapability::detach(QWidget* button) {
  if (menuWidget_ != nullptr) {
    menuWidget_->hide();
    menuWidget_->deleteLater();
    menuWidget_ = nullptr;
  }
  ButtonCapability::detach(button);
}

bool MenuCapability::isEnabled() const {
  return button_ != nullptr && !items_.empty();
}

void MenuCapability::setMenuItems(std::vector<MenuItem> items) {
  items_ = std::move(items);
  if (menuWidget_ == nullptr) {
    initMenu();
  } else {
    menuWidget_->setActions(items_);
  }
}

void MenuCapability::showMenu() {
  if (menuWidget_ == nullptr || button_ == nullptr) {
    return;
  }
  if (menuWidget_->isVisible()) {
    menuWidget_->hide();
    return;
  }
  menuWidget_->showForAnchor(button_);
}

void MenuCapability::initMenu() {
  if (button_ == nullptr || items_.empty()) {
    return;
  }
  menuWidget_ = new DropdownMenu(button_);
  connect(menuWidget_, &DropdownMenu::itemSelected, this,
          [this](const QVariant& data) { emit menuTriggered(regionId_, data); });
  menuWidget_->setActions(items_);
}

}  // namespace sli::toolkit::buttons
