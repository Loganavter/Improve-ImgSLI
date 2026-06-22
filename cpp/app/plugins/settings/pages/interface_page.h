#pragma once

#include "plugins/settings/pages/page.h"

class QButtonGroup;

namespace sli::toolkit {
class ComboBox;
class RadioButton;
class SpinBox;
}  // namespace sli::toolkit

namespace imgsli::app::settings_pages {

class InterfacePage final : public SettingsPage {
  Q_OBJECT
 public:
  explicit InterfacePage(QWidget* parent = nullptr);
  void load(const QJsonObject& obj) override;
  void save(QJsonObject& obj) const override;

 private:
  void syncFontCustomVisibility();

  sli::toolkit::RadioButton* ui_beginner_;
  sli::toolkit::RadioButton* ui_advanced_;
  sli::toolkit::RadioButton* ui_expert_;
  QButtonGroup* ui_mode_group_;
  sli::toolkit::RadioButton* font_builtin_;
  sli::toolkit::RadioButton* font_system_default_;
  sli::toolkit::RadioButton* font_system_custom_;
  QButtonGroup* font_mode_group_;
  sli::toolkit::ComboBox* font_family_;
  QWidget* font_family_row_;
  sli::toolkit::SpinBox* max_name_length_;
};

}  // namespace imgsli::app::settings_pages
