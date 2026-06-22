// Settings dialog shell.
//
// Hosts the C++ Qt port of `src/plugins/settings/dialog*.py`. The actual
// per-page widget construction and JSON round-trip lives in
// `plugins/settings/pages/<name>_page.{h,cpp}`. This file owns only the
// sidebar/stack composition, the OK/Cancel footer, and the Rust-backed
// normalization round-trip.

#pragma once

#include <QDialog>
#include <QJsonObject>
#include <QSize>

class QListWidget;
class QStackedWidget;
class QWidget;

namespace sli::toolkit {
class Button;
}

namespace imgsli::app::settings_pages {
class AnalysisPage;
class GeneralPage;
class InterfacePage;
class PerformancePage;
}  // namespace imgsli::app::settings_pages

namespace imgsli::app {

class Store;

class SettingsDialog final : public QDialog {
  Q_OBJECT

 public:
  // `store` is optional. When provided it is used to seed the dialog with live
  // state instead of the Rust-derived defaults (mirrors Python
  // `SettingsDialog.__init__` receiving `store=store`).
  explicit SettingsDialog(Store* store = nullptr, QWidget* parent = nullptr);

  void loadFromJson(const QString& json);
  QString normalizedJson() const;

 private slots:
  void updateStyles();

 private:
  void buildSidebar();
  QSize calculateDialogSize() const;
  QJsonObject readUi() const;
  void applyUi(const QJsonObject& obj);

  Store* store_;

  QListWidget* sidebar_;
  QStackedWidget* pages_;

  settings_pages::GeneralPage* general_page_;
  settings_pages::InterfacePage* interface_page_;
  settings_pages::PerformancePage* performance_page_;
  settings_pages::AnalysisPage* analysis_page_;

  sli::toolkit::Button* ok_;
  sli::toolkit::Button* cancel_;
};

}  // namespace imgsli::app
