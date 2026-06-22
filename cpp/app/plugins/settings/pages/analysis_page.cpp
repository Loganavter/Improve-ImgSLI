#include "plugins/settings/pages/analysis_page.h"

#include <QVBoxLayout>

#include "shell/i18n_helper.h"
#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/atomic/group_box.h"

namespace imgsli::app::settings_pages {

AnalysisPage::AnalysisPage(QWidget* parent) : SettingsPage(parent) {
  using imgsli::app::tr;
  auto* layout = new QVBoxLayout(this);

  auto* auto_group =
      new sli::toolkit::GroupBox(tr(QStringLiteral("settings.auto")), this);
  auto_crop_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.autocrop_black_borders_on_load")));
  auto_group->addWidget(auto_crop_);
  layout->addWidget(auto_group);

  auto* metrics_group =
      new sli::toolkit::GroupBox(tr(QStringLiteral("label.details")), this);
  auto_psnr_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.autocalculate_psnr")));
  metrics_group->addWidget(auto_psnr_);
  auto_ssim_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.autocalculate_ssim")));
  metrics_group->addWidget(auto_ssim_);
  layout->addWidget(metrics_group);

  layout->addStretch();
}

void AnalysisPage::load(const QJsonObject& obj) {
  auto_crop_->setChecked(
      obj.value(QStringLiteral("auto_crop_black_borders")).toBool(true));
  auto_psnr_->setChecked(
      obj.value(QStringLiteral("auto_calculate_psnr")).toBool(false));
  auto_ssim_->setChecked(
      obj.value(QStringLiteral("auto_calculate_ssim")).toBool(false));
}

void AnalysisPage::save(QJsonObject& obj) const {
  obj[QStringLiteral("auto_crop_black_borders")] = auto_crop_->isChecked();
  obj[QStringLiteral("auto_calculate_psnr")] = auto_psnr_->isChecked();
  obj[QStringLiteral("auto_calculate_ssim")] = auto_ssim_->isChecked();
}

}  // namespace imgsli::app::settings_pages
