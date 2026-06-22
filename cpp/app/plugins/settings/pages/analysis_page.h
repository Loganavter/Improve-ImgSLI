#pragma once

#include "plugins/settings/pages/page.h"

namespace sli::toolkit {
class CheckBox;
}

namespace imgsli::app::settings_pages {

class AnalysisPage final : public SettingsPage {
  Q_OBJECT
 public:
  explicit AnalysisPage(QWidget* parent = nullptr);
  void load(const QJsonObject& obj) override;
  void save(QJsonObject& obj) const override;

 private:
  sli::toolkit::CheckBox* auto_crop_;
  sli::toolkit::CheckBox* auto_psnr_;
  sli::toolkit::CheckBox* auto_ssim_;
};

}  // namespace imgsli::app::settings_pages
