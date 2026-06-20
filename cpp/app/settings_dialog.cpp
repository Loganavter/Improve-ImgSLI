#include "settings_dialog.h"

#include <QButtonGroup>
#include <QFontDatabase>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QListWidget>
#include <QStackedWidget>
#include <QString>
#include <QVBoxLayout>
#include <QWidget>

#include <exception>
#include <string>

#include "imgsli_core_bridge/bridge.h"
#include "sli/toolkit/button.h"
#include "sli/toolkit/check_box.h"
#include "sli/toolkit/combo_box.h"
#include "sli/toolkit/group_box.h"
#include "sli/toolkit/radio_button.h"
#include "sli/toolkit/spin_box.h"

namespace imgsli::app {

namespace {

QString rs_to_q(const rust::String& s) {
  return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

}  // namespace

SettingsDialog::SettingsDialog(QWidget* parent) : QDialog(parent) {
  setWindowTitle(tr("Settings"));
  setMinimumSize(640, 480);

  auto* root = new QVBoxLayout(this);
  auto* body = new QHBoxLayout();
  root->addLayout(body, 1);

  sidebar_ = new QListWidget(this);
  sidebar_->setFixedWidth(180);
  pages_ = new QStackedWidget(this);
  body->addWidget(sidebar_);
  body->addWidget(pages_, 1);

  buildGeneralPage();
  buildInterfacePage();
  buildPerformancePage();
  buildAnalysisPage();
  buildSidebar();
  connect(sidebar_, &QListWidget::currentRowChanged, pages_,
          &QStackedWidget::setCurrentIndex);
  sidebar_->setCurrentRow(0);

  auto* footer = new QHBoxLayout();
  footer->addStretch(1);
  cancel_ = new sli::toolkit::Button(tr("Cancel"),
                                     sli::toolkit::Button::Variant::Surface,
                                     this);
  ok_ = new sli::toolkit::Button(tr("OK"),
                                 sli::toolkit::Button::Variant::Default, this);
  footer->addWidget(cancel_);
  footer->addWidget(ok_);
  root->addLayout(footer);

  connect(ok_, &sli::toolkit::Button::clicked, this, &QDialog::accept);
  connect(cancel_, &sli::toolkit::Button::clicked, this, &QDialog::reject);

  loadFromJson(rs_to_q(imgsli::settings_dialog_default_json()));
}

void SettingsDialog::buildSidebar() {
  sidebar_->addItem(tr("General"));
  sidebar_->addItem(tr("Interface"));
  sidebar_->addItem(tr("Performance"));
  sidebar_->addItem(tr("Analysis"));
}

void SettingsDialog::buildGeneralPage() {
  auto* page = new QWidget(pages_);
  auto* layout = new QVBoxLayout(page);

  auto* lang_group = new sli::toolkit::GroupBox(tr("Language"), page);
  auto* lang_row = new QHBoxLayout();
  lang_row->setContentsMargins(5, 5, 5, 5);
  lang_en_ = new sli::toolkit::RadioButton(QStringLiteral("English"));
  lang_ru_ = new sli::toolkit::RadioButton(QStringLiteral("Русский"));
  lang_zh_ = new sli::toolkit::RadioButton(QStringLiteral("中文"));
  lang_pt_ = new sli::toolkit::RadioButton(QStringLiteral("Português"));
  lang_group_ = new QButtonGroup(this);
  for (auto* rb : {lang_en_, lang_ru_, lang_zh_, lang_pt_}) {
    lang_group_->addButton(rb);
    lang_row->addWidget(rb);
  }
  lang_row->addStretch();
  lang_group->addLayout(lang_row);
  layout->addWidget(lang_group);

  auto* sys_group = new sli::toolkit::GroupBox(tr("Appearance"), page);
  auto* theme_row = new QHBoxLayout();
  theme_row->setContentsMargins(5, 5, 5, 5);
  theme_row->addWidget(new QLabel(tr("Theme:")));
  theme_ = new sli::toolkit::ComboBox();
  theme_->setFixedWidth(140);
  theme_->addItem(tr("Auto"), QStringLiteral("auto"));
  theme_->addItem(tr("Light"), QStringLiteral("light"));
  theme_->addItem(tr("Dark"), QStringLiteral("dark"));
  theme_row->addWidget(theme_);
  theme_row->addStretch();
  sys_group->addLayout(theme_row);

  system_notifications_ =
      new sli::toolkit::CheckBox(tr("Enable system notifications"));
  sys_group->addWidget(system_notifications_);
  debug_logging_ = new sli::toolkit::CheckBox(tr("Enable debug logging"));
  sys_group->addWidget(debug_logging_);
  show_workspace_tabs_ =
      new sli::toolkit::CheckBox(tr("Show workspace tabs"));
  sys_group->addWidget(show_workspace_tabs_);
  layout->addWidget(sys_group);

  layout->addStretch();
  pages_->addWidget(page);
}

void SettingsDialog::buildInterfacePage() {
  auto* page = new QWidget(pages_);
  auto* layout = new QVBoxLayout(page);

  auto* mode_group = new sli::toolkit::GroupBox(tr("UI mode"), page);
  auto* mode_row = new QHBoxLayout();
  mode_row->setContentsMargins(5, 5, 5, 5);
  ui_beginner_ = new sli::toolkit::RadioButton(tr("Beginner"));
  ui_advanced_ = new sli::toolkit::RadioButton(tr("Advanced"));
  ui_expert_ = new sli::toolkit::RadioButton(tr("Expert"));
  ui_mode_group_ = new QButtonGroup(this);
  for (auto* rb : {ui_beginner_, ui_advanced_, ui_expert_}) {
    ui_mode_group_->addButton(rb);
    mode_row->addWidget(rb);
  }
  mode_row->addStretch();
  mode_group->addLayout(mode_row);
  layout->addWidget(mode_group);

  auto* font_group = new sli::toolkit::GroupBox(tr("UI font"), page);
  auto* font_radio_col = new QVBoxLayout();
  font_radio_col->setContentsMargins(5, 5, 5, 5);
  font_builtin_ = new sli::toolkit::RadioButton(tr("Built-in"));
  font_system_default_ = new sli::toolkit::RadioButton(tr("System default"));
  font_system_custom_ = new sli::toolkit::RadioButton(tr("Custom"));
  font_mode_group_ = new QButtonGroup(this);
  for (auto* rb : {font_builtin_, font_system_default_, font_system_custom_}) {
    font_mode_group_->addButton(rb);
    font_radio_col->addWidget(rb);
  }
  font_group->addLayout(font_radio_col);

  font_family_row_ = new QWidget(page);
  auto* fc_layout = new QHBoxLayout(font_family_row_);
  fc_layout->setContentsMargins(5, 0, 5, 5);
  font_family_ = new sli::toolkit::ComboBox();
  font_family_->setFixedWidth(320);
  for (const QString& fam : QFontDatabase::families()) {
    font_family_->addItem(fam, fam);
  }
  fc_layout->addWidget(font_family_);
  fc_layout->addStretch();
  font_group->addWidget(font_family_row_);
  layout->addWidget(font_group);

  for (auto* rb : {font_builtin_, font_system_default_, font_system_custom_}) {
    connect(rb, &sli::toolkit::RadioButton::toggled, this,
            &SettingsDialog::syncFontCustomVisibility);
  }

  auto* len_group =
      new sli::toolkit::GroupBox(tr("Maximum filename length"), page);
  auto* len_row = new QHBoxLayout();
  len_row->setContentsMargins(12, 5, 12, 5);
  // Range mirrors AppConstants.MIN_NAME_LENGTH_LIMIT / MAX_NAME_LENGTH_LIMIT
  // and imgsli_core::settings_dialog::limits.
  max_name_length_ = new sli::toolkit::SpinBox();
  max_name_length_->setRange(10, 150);
  max_name_length_->setFixedWidth(100);
  max_name_length_->setAlignment(Qt::AlignCenter);
  len_row->addWidget(max_name_length_);
  len_row->addStretch();
  len_group->addLayout(len_row);
  layout->addWidget(len_group);

  layout->addStretch();
  pages_->addWidget(page);
}

void SettingsDialog::buildPerformancePage() {
  auto* page = new QWidget(pages_);
  auto* layout = new QVBoxLayout(page);

  auto* res_group =
      new sli::toolkit::GroupBox(tr("Display cache resolution"), page);
  auto* res_row = new QHBoxLayout();
  res_row->setContentsMargins(5, 5, 5, 5);
  resolution_ = new sli::toolkit::ComboBox();
  resolution_->setMinimumWidth(180);
  // Mirrors AppConstants.DISPLAY_RESOLUTION_OPTIONS.
  resolution_->addItem(tr("Original"), 0);
  resolution_->addItem(tr("8K (4320p)"), 4320);
  resolution_->addItem(tr("4K (2160p)"), 2160);
  resolution_->addItem(tr("2K (1440p)"), 1440);
  resolution_->addItem(tr("Full HD (1080p)"), 1080);
  res_row->addWidget(resolution_, 1);
  res_group->addLayout(res_row);
  layout->addWidget(res_group);

  auto* opt_group =
      new sli::toolkit::GroupBox(tr("Interactive optimization"), page);

  const auto populate_interp = [](sli::toolkit::ComboBox* combo) {
    combo->addItem(QObject::tr("Nearest neighbor"), QStringLiteral("NEAREST"));
    combo->addItem(QObject::tr("Bilinear"), QStringLiteral("BILINEAR"));
    combo->addItem(QObject::tr("Bicubic"), QStringLiteral("BICUBIC"));
    combo->addItem(QObject::tr("Lanczos"), QStringLiteral("LANCZOS"));
    combo->addItem(QObject::tr("EWA Lanczos"),
                   QStringLiteral("EWA_LANCZOS"));
  };

  auto* zoom_row = new QHBoxLayout();
  zoom_row->setContentsMargins(0, 5, 0, 5);
  zoom_row->addWidget(new QLabel(tr("Zoom interpolation:")));
  zoom_interp_ = new sli::toolkit::ComboBox();
  zoom_interp_->setMinimumWidth(140);
  // Zoom combo only exposes the two safe methods (matches Python).
  zoom_interp_->addItem(tr("Nearest neighbor"), QStringLiteral("NEAREST"));
  zoom_interp_->addItem(tr("Bilinear"), QStringLiteral("BILINEAR"));
  zoom_row->addWidget(zoom_interp_, 1);
  opt_group->addLayout(zoom_row);

  auto* mag_row = new QHBoxLayout();
  mag_row->setContentsMargins(0, 5, 0, 5);
  optimize_movement_ =
      new sli::toolkit::CheckBox(tr("Optimize magnifier movement"));
  mag_interp_ = new sli::toolkit::ComboBox();
  mag_interp_->setMinimumWidth(140);
  populate_interp(mag_interp_);
  mag_row->addWidget(optimize_movement_);
  mag_row->addWidget(mag_interp_, 1);
  opt_group->addLayout(mag_row);
  connect(optimize_movement_, &sli::toolkit::CheckBox::toggled, mag_interp_,
          &QWidget::setEnabled);

  auto* laser_row = new QHBoxLayout();
  laser_row->setContentsMargins(0, 5, 0, 5);
  laser_smoothing_ =
      new sli::toolkit::CheckBox(tr("Optimize laser smoothing"));
  laser_interp_ = new sli::toolkit::ComboBox();
  laser_interp_->setMinimumWidth(140);
  populate_interp(laser_interp_);
  laser_row->addWidget(laser_smoothing_);
  laser_row->addWidget(laser_interp_, 1);
  opt_group->addLayout(laser_row);
  connect(laser_smoothing_, &sli::toolkit::CheckBox::toggled, laser_interp_,
          &QWidget::setEnabled);

  mag_intersection_highlight_ = new sli::toolkit::CheckBox(
      tr("Highlight magnifier intersections"));
  opt_group->addWidget(mag_intersection_highlight_);

  mag_auto_color_ = new sli::toolkit::CheckBox(
      tr("Auto-color new magnifier instances"));
  opt_group->addWidget(mag_auto_color_);
  layout->addWidget(opt_group);

  auto* video_group =
      new sli::toolkit::GroupBox(tr("Video recording"), page);
  auto* video_row = new QHBoxLayout();
  video_row->setContentsMargins(5, 5, 5, 5);
  video_row->addWidget(new QLabel(tr("Recording FPS:")));
  video_fps_ = new sli::toolkit::SpinBox();
  video_fps_->setRange(10, 144);
  video_fps_->setFixedWidth(100);
  video_fps_->setAlignment(Qt::AlignCenter);
  video_row->addWidget(video_fps_);
  video_row->addStretch();
  video_group->addLayout(video_row);
  layout->addWidget(video_group);

  auto* backend_group =
      new sli::toolkit::GroupBox(tr("Render backend"), page);
  auto* backend_row = new QHBoxLayout();
  backend_row->setContentsMargins(5, 5, 5, 5);
  backend_row->addWidget(new QLabel(tr("Backend:")));
  rhi_backend_ = new sli::toolkit::ComboBox();
  rhi_backend_->setMinimumWidth(180);
  rhi_backend_->addItem(tr("Default"), QStringLiteral("default"));
  rhi_backend_->addItem(QStringLiteral("OpenGL"), QStringLiteral("opengl"));
  rhi_backend_->addItem(QStringLiteral("Vulkan"), QStringLiteral("vulkan"));
#if defined(Q_OS_WIN)
  rhi_backend_->addItem(QStringLiteral("Direct3D 11"),
                        QStringLiteral("d3d11"));
  rhi_backend_->addItem(QStringLiteral("Direct3D 12"),
                        QStringLiteral("d3d12"));
#elif defined(Q_OS_MACOS)
  rhi_backend_->addItem(QStringLiteral("Metal"), QStringLiteral("metal"));
#endif
  rhi_backend_->addItem(QStringLiteral("Null"), QStringLiteral("null"));
  backend_row->addWidget(rhi_backend_, 1);
  backend_group->addLayout(backend_row);

  auto* hint = new QLabel(tr("Restart required after changing the backend."));
  hint->setWordWrap(true);
  backend_group->addWidget(hint);
  layout->addWidget(backend_group);

  layout->addStretch();
  pages_->addWidget(page);
}

void SettingsDialog::buildAnalysisPage() {
  auto* page = new QWidget(pages_);
  auto* layout = new QVBoxLayout(page);

  auto* auto_group = new sli::toolkit::GroupBox(tr("Automatic"), page);
  auto_crop_ =
      new sli::toolkit::CheckBox(tr("Auto-crop black borders on load"));
  auto_group->addWidget(auto_crop_);
  layout->addWidget(auto_group);

  auto* metrics_group = new sli::toolkit::GroupBox(tr("Metrics"), page);
  auto_psnr_ = new sli::toolkit::CheckBox(tr("Auto-calculate PSNR"));
  metrics_group->addWidget(auto_psnr_);
  auto_ssim_ = new sli::toolkit::CheckBox(tr("Auto-calculate SSIM"));
  metrics_group->addWidget(auto_ssim_);
  layout->addWidget(metrics_group);

  layout->addStretch();
  pages_->addWidget(page);
}

void SettingsDialog::syncFontCustomVisibility() {
  if (font_family_row_ != nullptr) {
    font_family_row_->setVisible(font_system_custom_->isChecked());
  }
}

void SettingsDialog::loadFromJson(const QString& json) {
  const QJsonDocument doc =
      QJsonDocument::fromJson(json.toUtf8());
  if (!doc.isObject()) {
    return;
  }
  applyUi(doc.object());
}

void SettingsDialog::applyUi(const QJsonObject& obj) {
  const QString lang = obj.value(QStringLiteral("language")).toString("en");
  if (lang == QStringLiteral("ru")) {
    lang_ru_->setChecked(true);
  } else if (lang == QStringLiteral("zh")) {
    lang_zh_->setChecked(true);
  } else if (lang == QStringLiteral("pt_BR")) {
    lang_pt_->setChecked(true);
  } else {
    lang_en_->setChecked(true);
  }

  const QString theme = obj.value(QStringLiteral("theme")).toString("auto");
  const int themeIdx = theme_->findData(theme);
  theme_->setCurrentIndex(themeIdx >= 0 ? themeIdx : 0);

  system_notifications_->setChecked(
      obj.value(QStringLiteral("system_notifications_enabled")).toBool(true));
  debug_logging_->setChecked(
      obj.value(QStringLiteral("debug_enabled")).toBool(false));
  show_workspace_tabs_->setChecked(
      obj.value(QStringLiteral("show_workspace_tabs")).toBool(false));

  const QString uiMode =
      obj.value(QStringLiteral("ui_mode")).toString("beginner");
  if (uiMode == QStringLiteral("expert")) {
    ui_expert_->setChecked(true);
  } else if (uiMode == QStringLiteral("advanced")) {
    ui_advanced_->setChecked(true);
  } else {
    ui_beginner_->setChecked(true);
  }

  const QString fontMode =
      obj.value(QStringLiteral("ui_font_mode")).toString("builtin");
  if (fontMode == QStringLiteral("system_default") ||
      fontMode == QStringLiteral("system")) {
    font_system_default_->setChecked(true);
  } else if (fontMode == QStringLiteral("system_custom")) {
    font_system_custom_->setChecked(true);
  } else {
    font_builtin_->setChecked(true);
  }
  const QString fontFamily =
      obj.value(QStringLiteral("ui_font_family")).toString();
  const int famIdx = font_family_->findData(fontFamily);
  if (famIdx >= 0) {
    font_family_->setCurrentIndex(famIdx);
  }
  syncFontCustomVisibility();

  max_name_length_->setValue(
      obj.value(QStringLiteral("max_name_length")).toInt(50));

  const int resolution =
      obj.value(QStringLiteral("resolution_limit")).toInt(2160);
  const int resIdx = resolution_->findData(resolution);
  resolution_->setCurrentIndex(resIdx >= 0 ? resIdx : 2);  // default: 4K

  const auto setComboData = [](sli::toolkit::ComboBox* combo,
                               const QString& data, const QString& fallback) {
    int idx = combo->findData(data);
    if (idx < 0) {
      idx = combo->findData(fallback);
    }
    if (idx >= 0) {
      combo->setCurrentIndex(idx);
    }
  };
  setComboData(zoom_interp_,
               obj.value(QStringLiteral("zoom_interpolation_method"))
                   .toString("BILINEAR"),
               QStringLiteral("BILINEAR"));
  setComboData(mag_interp_,
               obj.value(QStringLiteral("magnifier_interpolation_method"))
                   .toString("BILINEAR"),
               QStringLiteral("BILINEAR"));
  setComboData(laser_interp_,
               obj.value(QStringLiteral("laser_interpolation_method"))
                   .toString("BILINEAR"),
               QStringLiteral("BILINEAR"));

  optimize_movement_->setChecked(
      obj.value(QStringLiteral("optimize_magnifier_movement")).toBool(true));
  mag_interp_->setEnabled(optimize_movement_->isChecked());
  laser_smoothing_->setChecked(
      obj.value(QStringLiteral("optimize_laser_smoothing")).toBool(true));
  laser_interp_->setEnabled(laser_smoothing_->isChecked());
  mag_intersection_highlight_->setChecked(
      obj.value(QStringLiteral("magnifier_intersection_highlight_enabled"))
          .toBool(false));
  mag_auto_color_->setChecked(
      obj.value(QStringLiteral("magnifier_auto_color_new_instances"))
          .toBool(false));

  video_fps_->setValue(
      obj.value(QStringLiteral("video_recording_fps")).toInt(60));

  setComboData(rhi_backend_,
               obj.value(QStringLiteral("rhi_backend")).toString("default"),
               QStringLiteral("default"));

  auto_crop_->setChecked(
      obj.value(QStringLiteral("auto_crop_black_borders")).toBool(true));
  auto_psnr_->setChecked(
      obj.value(QStringLiteral("auto_calculate_psnr")).toBool(false));
  auto_ssim_->setChecked(
      obj.value(QStringLiteral("auto_calculate_ssim")).toBool(false));
}

QJsonObject SettingsDialog::readUi() const {
  QString lang = QStringLiteral("en");
  if (lang_ru_->isChecked()) {
    lang = QStringLiteral("ru");
  } else if (lang_zh_->isChecked()) {
    lang = QStringLiteral("zh");
  } else if (lang_pt_->isChecked()) {
    lang = QStringLiteral("pt_BR");
  }

  // Start from defaults so fields not yet exposed in the UI keep sane values.
  const QString defaultsJson = rs_to_q(imgsli::settings_dialog_default_json());
  QJsonObject obj =
      QJsonDocument::fromJson(defaultsJson.toUtf8()).object();
  obj[QStringLiteral("language")] = lang;
  obj[QStringLiteral("theme")] =
      theme_->currentData().toString().isEmpty()
          ? QStringLiteral("auto")
          : theme_->currentData().toString();
  obj[QStringLiteral("system_notifications_enabled")] =
      system_notifications_->isChecked();
  obj[QStringLiteral("debug_enabled")] = debug_logging_->isChecked();
  obj[QStringLiteral("show_workspace_tabs")] =
      show_workspace_tabs_->isChecked();

  QString uiMode = QStringLiteral("beginner");
  if (ui_expert_->isChecked()) {
    uiMode = QStringLiteral("expert");
  } else if (ui_advanced_->isChecked()) {
    uiMode = QStringLiteral("advanced");
  }
  obj[QStringLiteral("ui_mode")] = uiMode;

  QString fontMode = QStringLiteral("builtin");
  if (font_system_default_->isChecked()) {
    fontMode = QStringLiteral("system_default");
  } else if (font_system_custom_->isChecked()) {
    fontMode = QStringLiteral("system_custom");
  }
  obj[QStringLiteral("ui_font_mode")] = fontMode;
  obj[QStringLiteral("ui_font_family")] =
      font_family_->currentData().toString();

  obj[QStringLiteral("max_name_length")] = max_name_length_->value();

  obj[QStringLiteral("resolution_limit")] =
      resolution_->currentData().toInt();
  obj[QStringLiteral("zoom_interpolation_method")] =
      zoom_interp_->currentData().toString();
  obj[QStringLiteral("magnifier_interpolation_method")] =
      mag_interp_->currentData().toString();
  obj[QStringLiteral("laser_interpolation_method")] =
      laser_interp_->currentData().toString();
  obj[QStringLiteral("optimize_magnifier_movement")] =
      optimize_movement_->isChecked();
  obj[QStringLiteral("optimize_laser_smoothing")] =
      laser_smoothing_->isChecked();
  obj[QStringLiteral("magnifier_intersection_highlight_enabled")] =
      mag_intersection_highlight_->isChecked();
  obj[QStringLiteral("magnifier_auto_color_new_instances")] =
      mag_auto_color_->isChecked();
  obj[QStringLiteral("video_recording_fps")] = video_fps_->value();
  obj[QStringLiteral("rhi_backend")] =
      rhi_backend_->currentData().toString();

  obj[QStringLiteral("auto_crop_black_borders")] = auto_crop_->isChecked();
  obj[QStringLiteral("auto_calculate_psnr")] = auto_psnr_->isChecked();
  obj[QStringLiteral("auto_calculate_ssim")] = auto_ssim_->isChecked();
  return obj;
}

QString SettingsDialog::normalizedJson() const {
  const QJsonObject obj = readUi();
  const QString raw =
      QString::fromUtf8(QJsonDocument(obj).toJson(QJsonDocument::Compact));
  try {
    const QByteArray utf8 = raw.toUtf8();
    return rs_to_q(imgsli::settings_dialog_normalize_json(
        std::string(utf8.constData(),
                    static_cast<std::size_t>(utf8.size()))));
  } catch (const std::exception&) {
    return raw;
  }
}

}  // namespace imgsli::app
