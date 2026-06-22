#include "plugins/settings/pages/interface_page.h"

#include <QButtonGroup>
#include <QFontDatabase>
#include <QHBoxLayout>
#include <QVBoxLayout>

#include "shell/i18n_helper.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "sli/toolkit/atomic/group_box.h"
#include "sli/toolkit/atomic/radio_button.h"
#include "sli/toolkit/atomic/spin_box.h"

namespace imgsli::app::settings_pages {

InterfacePage::InterfacePage(QWidget* parent) : SettingsPage(parent) {
  using imgsli::app::tr;
  auto* layout = new QVBoxLayout(this);

  auto* mode_group =
      new sli::toolkit::GroupBox(tr(QStringLiteral("settings.ui_mode")), this);
  auto* mode_row = new QHBoxLayout();
  mode_row->setContentsMargins(5, 5, 5, 5);
  ui_beginner_ = new sli::toolkit::RadioButton(
      tr(QStringLiteral("settings.ui_mode_beginner")));
  ui_advanced_ = new sli::toolkit::RadioButton(
      tr(QStringLiteral("settings.ui_mode_advanced")));
  ui_expert_ = new sli::toolkit::RadioButton(
      tr(QStringLiteral("settings.ui_mode_expert")));
  ui_mode_group_ = new QButtonGroup(this);
  for (auto* rb : {ui_beginner_, ui_advanced_, ui_expert_}) {
    ui_mode_group_->addButton(rb);
    mode_row->addWidget(rb);
  }
  mode_row->addStretch();
  mode_group->addLayout(mode_row);
  layout->addWidget(mode_group);

  auto* font_group =
      new sli::toolkit::GroupBox(tr(QStringLiteral("settings.ui_font")), this);
  auto* font_radio_col = new QVBoxLayout();
  font_radio_col->setContentsMargins(5, 5, 5, 5);
  font_builtin_ = new sli::toolkit::RadioButton(
      tr(QStringLiteral("settings.builtin_font")));
  font_system_default_ = new sli::toolkit::RadioButton(
      tr(QStringLiteral("settings.system_default")));
  font_system_custom_ = new sli::toolkit::RadioButton(
      tr(QStringLiteral("settings.custom")));
  font_mode_group_ = new QButtonGroup(this);
  for (auto* rb : {font_builtin_, font_system_default_, font_system_custom_}) {
    font_mode_group_->addButton(rb);
    font_radio_col->addWidget(rb);
  }
  font_group->addLayout(font_radio_col);

  font_family_row_ = new QWidget(this);
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
            &InterfacePage::syncFontCustomVisibility);
  }

  auto* len_group = new sli::toolkit::GroupBox(
      tr(QStringLiteral("settings.maximum_name_length_ui")), this);
  auto* len_row = new QHBoxLayout();
  len_row->setContentsMargins(12, 5, 12, 5);
  max_name_length_ = new sli::toolkit::SpinBox();
  max_name_length_->setRange(10, 150);
  max_name_length_->setFixedWidth(100);
  max_name_length_->setAlignment(Qt::AlignCenter);
  len_row->addWidget(max_name_length_);
  len_row->addStretch();
  len_group->addLayout(len_row);
  layout->addWidget(len_group);

  layout->addStretch();
}

void InterfacePage::syncFontCustomVisibility() {
  if (font_family_row_ != nullptr) {
    font_family_row_->setVisible(font_system_custom_->isChecked());
  }
}

void InterfacePage::load(const QJsonObject& obj) {
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
}

void InterfacePage::save(QJsonObject& obj) const {
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
}

}  // namespace imgsli::app::settings_pages
