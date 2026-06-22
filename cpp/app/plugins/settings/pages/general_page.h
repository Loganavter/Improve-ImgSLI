#pragma once

#include "plugins/settings/pages/page.h"

class QButtonGroup;

namespace sli::toolkit {
class CheckBox;
class ComboBox;
class RadioButton;
}  // namespace sli::toolkit

namespace imgsli::app::settings_pages {

class GeneralPage final : public SettingsPage {
  Q_OBJECT
 public:
  explicit GeneralPage(QWidget* parent = nullptr);
  void load(const QJsonObject& obj) override;
  void save(QJsonObject& obj) const override;

 private:
  sli::toolkit::RadioButton* lang_en_;
  sli::toolkit::RadioButton* lang_ru_;
  sli::toolkit::RadioButton* lang_zh_;
  sli::toolkit::RadioButton* lang_pt_;
  QButtonGroup* lang_group_;
  sli::toolkit::ComboBox* theme_;
  sli::toolkit::CheckBox* system_notifications_;
  sli::toolkit::CheckBox* debug_logging_;
  sli::toolkit::CheckBox* show_workspace_tabs_;
};

}  // namespace imgsli::app::settings_pages
