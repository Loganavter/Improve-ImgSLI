#pragma once

#include "plugins/settings/pages/page.h"

namespace sli::toolkit {
class CheckBox;
class ComboBox;
class SpinBox;
}  // namespace sli::toolkit

namespace imgsli::app::settings_pages {

class PerformancePage final : public SettingsPage {
  Q_OBJECT
 public:
  explicit PerformancePage(QWidget* parent = nullptr);
  void load(const QJsonObject& obj) override;
  void save(QJsonObject& obj) const override;

 private:
  sli::toolkit::ComboBox* resolution_;
  sli::toolkit::ComboBox* zoom_interp_;
  sli::toolkit::CheckBox* optimize_movement_;
  sli::toolkit::ComboBox* mag_interp_;
  sli::toolkit::CheckBox* laser_smoothing_;
  sli::toolkit::ComboBox* laser_interp_;
  sli::toolkit::CheckBox* mag_intersection_highlight_;
  sli::toolkit::CheckBox* mag_auto_color_;
  sli::toolkit::SpinBox* video_fps_;
  sli::toolkit::ComboBox* rhi_backend_;
};

}  // namespace imgsli::app::settings_pages
