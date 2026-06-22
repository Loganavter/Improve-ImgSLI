#include "plugins/settings/pages/general_page.h"

#include <QButtonGroup>
#include <QHBoxLayout>
#include <QLabel>
#include <QVBoxLayout>

#include "shell/i18n_helper.h"
#include "sli/toolkit/atomic/check_box.h"
#include "sli/toolkit/comboboxes/combo_box.h"
#include "sli/toolkit/atomic/group_box.h"
#include "sli/toolkit/atomic/radio_button.h"

namespace imgsli::app::settings_pages {

GeneralPage::GeneralPage(QWidget* parent) : SettingsPage(parent) {
  using imgsli::app::tr;
  auto* layout = new QVBoxLayout(this);

  auto* lang_group =
      new sli::toolkit::GroupBox(tr(QStringLiteral("label.language")), this);
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

  auto* sys_group =
      new sli::toolkit::GroupBox(tr(QStringLiteral("settings.appearance")), this);
  auto* theme_row = new QHBoxLayout();
  theme_row->setContentsMargins(5, 5, 5, 5);
  theme_row->addWidget(
      new QLabel(tr(QStringLiteral("label.theme")) + QStringLiteral(":")));
  theme_ = new sli::toolkit::ComboBox();
  theme_->setFixedWidth(140);
  theme_->addItem(tr(QStringLiteral("settings.auto")), QStringLiteral("auto"));
  theme_->addItem(tr(QStringLiteral("settings.light")),
                   QStringLiteral("light"));
  theme_->addItem(tr(QStringLiteral("settings.dark")), QStringLiteral("dark"));
  theme_row->addWidget(theme_);
  theme_row->addStretch();
  sys_group->addLayout(theme_row);

  system_notifications_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.system_notifications")));
  sys_group->addWidget(system_notifications_);
  debug_logging_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.enable_debug_logging")));
  sys_group->addWidget(debug_logging_);
  show_workspace_tabs_ = new sli::toolkit::CheckBox(
      tr(QStringLiteral("settings.show_workspace_tabs")));
  sys_group->addWidget(show_workspace_tabs_);
  layout->addWidget(sys_group);

  layout->addStretch();
}

void GeneralPage::load(const QJsonObject& obj) {
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
}

void GeneralPage::save(QJsonObject& obj) const {
  QString lang = QStringLiteral("en");
  if (lang_ru_->isChecked()) {
    lang = QStringLiteral("ru");
  } else if (lang_zh_->isChecked()) {
    lang = QStringLiteral("zh");
  } else if (lang_pt_->isChecked()) {
    lang = QStringLiteral("pt_BR");
  }
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
}

}  // namespace imgsli::app::settings_pages
