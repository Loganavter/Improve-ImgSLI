#include "plugins/settings/dialog.h"

#include <QHBoxLayout>
#include <QJsonDocument>
#include <QListWidget>
#include <QStackedWidget>
#include <QVBoxLayout>

#include <exception>
#include <string>

#include "imgsli_core_bridge/bridge.h"
#include "plugins/settings/pages/analysis_page.h"
#include "plugins/settings/pages/general_page.h"
#include "plugins/settings/pages/interface_page.h"
#include "plugins/settings/pages/performance_page.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"

namespace imgsli::app {

namespace {

QString rs_to_q(const rust::String& s) {
  return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

}  // namespace

SettingsDialog::SettingsDialog(QWidget* parent) : QDialog(parent) {
  using imgsli::app::tr;
  setWindowTitle(tr(QStringLiteral("settings.title")));
  setMinimumSize(640, 480);

  auto* root = new QVBoxLayout(this);
  auto* body = new QHBoxLayout();
  root->addLayout(body, 1);

  sidebar_ = new QListWidget(this);
  sidebar_->setFixedWidth(180);
  pages_ = new QStackedWidget(this);
  body->addWidget(sidebar_);
  body->addWidget(pages_, 1);

  general_page_ = new settings_pages::GeneralPage(pages_);
  interface_page_ = new settings_pages::InterfacePage(pages_);
  performance_page_ = new settings_pages::PerformancePage(pages_);
  analysis_page_ = new settings_pages::AnalysisPage(pages_);
  pages_->addWidget(general_page_);
  pages_->addWidget(interface_page_);
  pages_->addWidget(performance_page_);
  pages_->addWidget(analysis_page_);

  buildSidebar();
  connect(sidebar_, &QListWidget::currentRowChanged, pages_,
          &QStackedWidget::setCurrentIndex);
  sidebar_->setCurrentRow(0);

  auto* footer = new QHBoxLayout();
  footer->addStretch(1);
  cancel_ = new sli::toolkit::Button(tr(QStringLiteral("shared.cancel")),
                                      sli::toolkit::Button::Variant::Surface,
                                      this);
  ok_ = new sli::toolkit::Button(tr(QStringLiteral("shared.ok")),
                                  sli::toolkit::Button::Variant::Default, this);
  footer->addWidget(cancel_);
  footer->addWidget(ok_);
  root->addLayout(footer);

  connect(ok_, &sli::toolkit::Button::clicked, this, &QDialog::accept);
  connect(cancel_, &sli::toolkit::Button::clicked, this, &QDialog::reject);

  loadFromJson(rs_to_q(imgsli::settings_dialog_default_json()));
}

void SettingsDialog::buildSidebar() {
  using imgsli::app::tr;
  sidebar_->addItem(tr(QStringLiteral("settings.page_general")));
  sidebar_->addItem(tr(QStringLiteral("settings.page_interface")));
  sidebar_->addItem(tr(QStringLiteral("settings.page_performance")));
  sidebar_->addItem(tr(QStringLiteral("settings.page_analysis")));
}

void SettingsDialog::loadFromJson(const QString& json) {
  const QJsonDocument doc = QJsonDocument::fromJson(json.toUtf8());
  if (!doc.isObject()) {
    return;
  }
  applyUi(doc.object());
}

void SettingsDialog::applyUi(const QJsonObject& obj) {
  general_page_->load(obj);
  interface_page_->load(obj);
  performance_page_->load(obj);
  analysis_page_->load(obj);
}

QJsonObject SettingsDialog::readUi() const {
  const QString defaultsJson = rs_to_q(imgsli::settings_dialog_default_json());
  QJsonObject obj = QJsonDocument::fromJson(defaultsJson.toUtf8()).object();
  general_page_->save(obj);
  interface_page_->save(obj);
  performance_page_->save(obj);
  analysis_page_->save(obj);
  return obj;
}

QString SettingsDialog::normalizedJson() const {
  const QJsonObject obj = readUi();
  const QString raw =
      QString::fromUtf8(QJsonDocument(obj).toJson(QJsonDocument::Compact));
  try {
    const QByteArray utf8 = raw.toUtf8();
    return rs_to_q(imgsli::settings_dialog_normalize_json(std::string(
        utf8.constData(), static_cast<std::size_t>(utf8.size()))));
  } catch (const std::exception&) {
    return raw;
  }
}

}  // namespace imgsli::app
