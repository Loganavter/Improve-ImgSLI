#include "plugins/settings/dialog.h"

#include <QApplication>
#include <QHBoxLayout>
#include <QJsonDocument>
#include <QListWidget>
#include <QScreen>
#include <QScrollArea>
#include <QStackedWidget>
#include <QVBoxLayout>

#include <algorithm>
#include <exception>
#include <string>

#include "core/store.h"
#include "imgsli_core_bridge/bridge.h"
#include "plugins/settings/pages/analysis_page.h"
#include "plugins/settings/pages/general_page.h"
#include "plugins/settings/pages/interface_page.h"
#include "plugins/settings/pages/performance_page.h"
#include "shell/i18n_helper.h"
#include "sli/toolkit/buttons/button.h"
#include "sli/toolkit/theme.h"

namespace imgsli::app {

namespace {

QString rs_to_q(const rust::String& s) {
  return QString::fromUtf8(s.data(), static_cast<int>(s.size()));
}

}  // namespace

SettingsDialog::SettingsDialog(Store* store, QWidget* parent)
    : QDialog(parent), store_(store) {
  using imgsli::app::tr;
  setWindowTitle(tr(QStringLiteral("settings.title")));
  setMinimumSize(300, 200);

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

  // Seed dialog from the live store state when available; fall back to
  // Rust-generated defaults. Mirrors Python's `store` parameter path.
  if (store_ != nullptr) {
    const QString stateJson = store_->stateJson();
    if (!stateJson.isEmpty()) {
      loadFromJson(stateJson);
    } else {
      loadFromJson(rs_to_q(imgsli::settings_dialog_default_json()));
    }
  } else {
    loadFromJson(rs_to_q(imgsli::settings_dialog_default_json()));
  }

  // Mirror Python: theme_manager.theme_changed.connect(self._apply_styles)
  sli::toolkit::Theme::onThemeChanged(this, [this]() { updateStyles(); });

  // Apply dynamic geometry like Python's calculate_and_apply_geometry().
  ensurePolished();
  resize(calculateDialogSize());
  if (parentWidget() != nullptr) {
    QRect geo = geometry();
    geo.moveCenter(parentWidget()->geometry().center());
    move(geo.topLeft());
  }
}

void SettingsDialog::buildSidebar() {
  using imgsli::app::tr;
  sidebar_->addItem(tr(QStringLiteral("settings.page_general")));
  sidebar_->addItem(tr(QStringLiteral("settings.page_interface")));
  sidebar_->addItem(tr(QStringLiteral("settings.page_performance")));
  sidebar_->addItem(tr(QStringLiteral("settings.page_analysis")));
}

void SettingsDialog::updateStyles() {
  // Re-polish the dialog so theme-dependent QSS/palette propagates to all
  // child widgets. Mirrors Python's `apply_styles` → `polish_themed_dialog`.
  style()->polish(this);
  for (QWidget* child : findChildren<QWidget*>()) {
    child->style()->polish(child);
  }
  update();
}

QSize SettingsDialog::calculateDialogSize() const {
  // Mirrors Python's calculate_and_apply_geometry(): measure the widest page
  // content and the tallest page, then clamp to screen dimensions.
  int maxContentWidth = 0;
  int maxContentHeight = 0;

  for (int i = 0; i < pages_->count(); ++i) {
    QWidget* page = pages_->widget(i);
    if (page == nullptr) {
      continue;
    }
    // Pages may contain a QScrollArea wrapping the actual content.
    const auto* scroll = page->findChild<QScrollArea*>();
    QWidget* content = (scroll != nullptr) ? scroll->widget() : page;
    if (content != nullptr) {
      content->ensurePolished();
      content->adjustSize();
      maxContentWidth = std::max(maxContentWidth, content->sizeHint().width());
      maxContentHeight =
          std::max(maxContentHeight, content->sizeHint().height());
    }
  }

  const int sidebarWidth = sidebar_ ? sidebar_->width() : 180;
  const int marginExtra = 40;
  const int requiredWidth = sidebarWidth + maxContentWidth + marginExtra;
  const int finalWidth = std::max(800, std::min(requiredWidth, 1200));

  const int bottomControlsHeight = 80;
  const int sidebarReqHeight = pages_->count() * 45 + 40;
  const int requiredHeight =
      std::max(sidebarReqHeight, maxContentHeight + bottomControlsHeight);

  int screenHeight = 800;
  if (QScreen* screen = QApplication::primaryScreen()) {
    screenHeight = screen->availableGeometry().height();
  }
  const int finalHeight = std::min(requiredHeight, screenHeight - 100) + 5;

  return {finalWidth, finalHeight};
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
