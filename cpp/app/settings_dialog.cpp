#include "settings_dialog.h"

#include <QButtonGroup>
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
