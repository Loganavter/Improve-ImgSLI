// Settings dialog shell — initial Phase 4 surface.
//
// Hosts the C++ Qt port of `src/plugins/settings/dialog*.py`, bound to the
// `imgsli_core::settings_dialog::SettingsDialogData` view-model that flows
// through cxx. Only the General page is implemented so far; remaining pages
// will land alongside their feature ports.

#pragma once

#include <QDialog>
#include <QJsonObject>

class QButtonGroup;
class QListWidget;
class QStackedWidget;

class QWidget;

namespace sli::toolkit {
class Button;
class CheckBox;
class ComboBox;
class GroupBox;
class RadioButton;
class SpinBox;
}  // namespace sli::toolkit

namespace imgsli::app {

class SettingsDialog final : public QDialog {
  Q_OBJECT

 public:
  explicit SettingsDialog(QWidget* parent = nullptr);

  /// Populate widgets from a JSON-encoded `SettingsDialogData`.
  void loadFromJson(const QString& json);

  /// Read the current widget values into a `SettingsDialogData` and return
  /// the JSON encoding, normalized through the Rust core.
  QString normalizedJson() const;

 private:
  void buildSidebar();
  void buildGeneralPage();
  void buildInterfacePage();
  void buildPerformancePage();
  void buildAnalysisPage();
  QJsonObject readUi() const;
  void applyUi(const QJsonObject& obj);
  void syncFontCustomVisibility();

  QListWidget* sidebar_;
  QStackedWidget* pages_;

  // General page widgets.
  sli::toolkit::RadioButton* lang_en_;
  sli::toolkit::RadioButton* lang_ru_;
  sli::toolkit::RadioButton* lang_zh_;
  sli::toolkit::RadioButton* lang_pt_;
  QButtonGroup* lang_group_;
  sli::toolkit::ComboBox* theme_;
  sli::toolkit::CheckBox* system_notifications_;
  sli::toolkit::CheckBox* debug_logging_;
  sli::toolkit::CheckBox* show_workspace_tabs_;

  // Interface page widgets.
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

  // Performance page widgets.
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

  // Analysis page widgets.
  sli::toolkit::CheckBox* auto_crop_;
  sli::toolkit::CheckBox* auto_psnr_;
  sli::toolkit::CheckBox* auto_ssim_;

  sli::toolkit::Button* ok_;
  sli::toolkit::Button* cancel_;
};

}  // namespace imgsli::app
