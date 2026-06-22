#include "plugins/settings/pages/performance_page.h"

#include <QHBoxLayout>
#include <QLabel>
#include <QVBoxLayout>

#include "shell/i18n_helper.h"
#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "sli/toolkit/atomic/group_box.h"
#include "sli/toolkit/atomic/spin_box.h"

namespace imgsli::app::settings_pages {

namespace {

void populateInterpolation(sli::toolkit::ComboBox* combo) {
  combo->addItem(QObject::tr("Nearest neighbor"), QStringLiteral("NEAREST"));
  combo->addItem(QObject::tr("Bilinear"), QStringLiteral("BILINEAR"));
  combo->addItem(QObject::tr("Bicubic"), QStringLiteral("BICUBIC"));
  combo->addItem(QObject::tr("Lanczos"), QStringLiteral("LANCZOS"));
  combo->addItem(QObject::tr("EWA Lanczos"), QStringLiteral("EWA_LANCZOS"));
}

void setComboData(sli::toolkit::ComboBox* combo, const QString& data,
                  const QString& fallback) {
  int idx = combo->findData(data);
  if (idx < 0) {
    idx = combo->findData(fallback);
  }
  if (idx >= 0) {
    combo->setCurrentIndex(idx);
  }
}

}  // namespace

PerformancePage::PerformancePage(QWidget* parent) : SettingsPage(parent) {
  using imgsli::app::tr;
  auto* layout = new QVBoxLayout(this);

  auto* res_group = new sli::toolkit::GroupBox(
      tr(QStringLiteral("settings.display_cache_resolution")), this);
  auto* res_row = new QHBoxLayout();
  res_row->setContentsMargins(5, 5, 5, 5);
  resolution_ = new sli::toolkit::ComboBox();
  resolution_->setMinimumWidth(180);
  resolution_->addItem(tr(QStringLiteral("settings.original")), 0);
  resolution_->addItem(tr(QStringLiteral("settings.resolution_8k")), 4320);
  resolution_->addItem(tr(QStringLiteral("settings.resolution_4k")), 2160);
  resolution_->addItem(tr(QStringLiteral("settings.resolution_2k")), 1440);
  resolution_->addItem(tr(QStringLiteral("settings.resolution_full_hd")), 1080);
  res_row->addWidget(resolution_, 1);
  res_group->addLayout(res_row);
  layout->addWidget(res_group);

  auto* opt_group = new sli::toolkit::GroupBox(
      tr(QStringLiteral("settings.interactive_optimization")), this);

  auto* zoom_row = new QHBoxLayout();
  zoom_row->setContentsMargins(0, 5, 0, 5);
  zoom_row->addWidget(
      new QLabel(tr(QStringLiteral("settings.zoom_interpolation")) +
                 QStringLiteral(":")));
  zoom_interp_ = new sli::toolkit::ComboBox();
  zoom_interp_->setMinimumWidth(140);
  zoom_interp_->addItem(tr("Nearest neighbor"), QStringLiteral("NEAREST"));
  zoom_interp_->addItem(tr("Bilinear"), QStringLiteral("BILINEAR"));
  zoom_row->addWidget(zoom_interp_, 1);
  opt_group->addLayout(zoom_row);

  auto* mag_row = new QHBoxLayout();
  mag_row->setContentsMargins(0, 5, 0, 5);
  optimize_movement_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.optimize_magnifier_movement")));
  mag_interp_ = new sli::toolkit::ComboBox();
  mag_interp_->setMinimumWidth(140);
  populateInterpolation(mag_interp_);
  mag_row->addWidget(optimize_movement_);
  mag_row->addWidget(mag_interp_, 1);
  opt_group->addLayout(mag_row);
  connect(optimize_movement_, &sli::toolkit::CheckBox::toggled, mag_interp_,
          &QWidget::setEnabled);

  auto* laser_row = new QHBoxLayout();
  laser_row->setContentsMargins(0, 5, 0, 5);
  laser_smoothing_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.optimize_laser_smoothing")));
  laser_interp_ = new sli::toolkit::ComboBox();
  laser_interp_->setMinimumWidth(140);
  populateInterpolation(laser_interp_);
  laser_row->addWidget(laser_smoothing_);
  laser_row->addWidget(laser_interp_, 1);
  opt_group->addLayout(laser_row);
  connect(laser_smoothing_, &sli::toolkit::CheckBox::toggled, laser_interp_,
          &QWidget::setEnabled);

  mag_intersection_highlight_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.magnifier_intersection_highlight")));
  opt_group->addWidget(mag_intersection_highlight_);
  mag_auto_color_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.magnifier_auto_color_new_instances")));
  opt_group->addWidget(mag_auto_color_);
  layout->addWidget(opt_group);

  auto* video_group = new sli::toolkit::GroupBox(
      tr(QStringLiteral("settings.video_recording")), this);
  auto* video_row = new QHBoxLayout();
  video_row->setContentsMargins(5, 5, 5, 5);
  video_row->addWidget(new QLabel(
      tr(QStringLiteral("settings.recording_fps")) + QStringLiteral(":")));
  video_fps_ = new sli::toolkit::SpinBox();
  video_fps_->setRange(10, 144);
  video_fps_->setFixedWidth(100);
  video_fps_->setAlignment(Qt::AlignCenter);
  video_row->addWidget(video_fps_);
  video_row->addStretch();
  video_group->addLayout(video_row);
  layout->addWidget(video_group);

  auto* backend_group = new sli::toolkit::GroupBox(
      tr(QStringLiteral("settings.render_backend")), this);
  auto* backend_row = new QHBoxLayout();
  backend_row->setContentsMargins(5, 5, 5, 5);
  backend_row->addWidget(
      new QLabel(tr(QStringLiteral("settings.render_backend_label")) +
                 QStringLiteral(":")));
  rhi_backend_ = new sli::toolkit::ComboBox();
  rhi_backend_->setMinimumWidth(180);
  rhi_backend_->addItem(tr(QStringLiteral("settings.render_backend_default")),
                         QStringLiteral("default"));
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

  auto* hint = new QLabel(
      tr(QStringLiteral("settings.render_backend_restart_hint")));
  hint->setWordWrap(true);
  backend_group->addWidget(hint);
  layout->addWidget(backend_group);

  layout->addStretch();
}

void PerformancePage::load(const QJsonObject& obj) {
  const int resolution =
      obj.value(QStringLiteral("resolution_limit")).toInt(2160);
  const int resIdx = resolution_->findData(resolution);
  resolution_->setCurrentIndex(resIdx >= 0 ? resIdx : 2);
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
}

void PerformancePage::save(QJsonObject& obj) const {
  obj[QStringLiteral("resolution_limit")] = resolution_->currentData().toInt();
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
  obj[QStringLiteral("rhi_backend")] = rhi_backend_->currentData().toString();
}

}  // namespace imgsli::app::settings_pages
