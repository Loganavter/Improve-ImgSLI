#include "ui/managers/tray_manager.h"

#include "utils/resource_loader.h"

#include <QAction>
#include <QFileInfo>
#include <QIcon>
#include <QMenu>

namespace imgsli::app::ui::managers {

TrayManager::TrayManager(QObject* parent, QString appName)
    : QObject(parent), appName_(std::move(appName)) {
  if (!QSystemTrayIcon::isSystemTrayAvailable()) {
    return;
  }

  QIcon icon(utils::resourcePath(QStringLiteral("assets/icons/icon.png")));
  if (icon.isNull()) {
    icon = QIcon::fromTheme(QStringLiteral("application"));
  }

  tray_ = new QSystemTrayIcon(icon, this);
  tray_->setToolTip(appName_);

  buildContextMenu();
  connect(tray_, &QSystemTrayIcon::activated, this, &TrayManager::onActivated);
  connect(tray_, &QSystemTrayIcon::messageClicked, this,
          &TrayManager::openLastFolderRequested);

  if (!tray_->icon().isNull()) {
    tray_->show();
  }
}

TrayManager::~TrayManager() {
  if (tray_) {
    tray_->hide();
    tray_->setContextMenu(nullptr);
  }
}

void TrayManager::buildContextMenu() {
  if (!tray_) {
    return;
  }
  menu_ = new QMenu();
  auto add = [&](const QString& key) {
    auto* action = new QAction(menu_);
    actions_.insert(key, action);
    return action;
  };
  auto* toggle = add(QStringLiteral("toggle"));
  auto* openFile = add(QStringLiteral("open_file"));
  auto* openFolder = add(QStringLiteral("open_folder"));
  auto* quit = add(QStringLiteral("quit"));

  connect(toggle, &QAction::triggered, this,
          &TrayManager::toggleVisibilityRequested);
  connect(openFile, &QAction::triggered, this,
          &TrayManager::openLastFileRequested);
  connect(openFolder, &QAction::triggered, this,
          &TrayManager::openLastFolderRequested);
  connect(quit, &QAction::triggered, this, &TrayManager::quitRequested);

  openFile->setVisible(false);

  menu_->addAction(toggle);
  menu_->addSeparator();
  menu_->addAction(openFile);
  menu_->addAction(openFolder);
  menu_->addSeparator();
  menu_->addAction(quit);

  tray_->setContextMenu(menu_);
}

void TrayManager::retranslate(const QString& toggleText,
                              const QString& openFileText,
                              const QString& openFolderText,
                              const QString& quitText) {
  auto apply = [&](const QString& key, const QString& text) {
    if (text.isEmpty()) return;
    if (auto it = actions_.find(key); it != actions_.end()) {
      it.value()->setText(text);
    }
  };
  apply(QStringLiteral("toggle"), toggleText);
  apply(QStringLiteral("open_file"), openFileText);
  apply(QStringLiteral("open_folder"), openFolderText);
  apply(QStringLiteral("quit"), quitText);
}

void TrayManager::setLastSavedPath(const QString& path) {
  lastSavedPath_ = path;
  if (auto it = actions_.find(QStringLiteral("open_file"));
      it != actions_.end()) {
    it.value()->setVisible(!path.isEmpty() && QFileInfo(path).isFile());
  }
}

void TrayManager::showNotification(const QString& title, const QString& message,
                                   int timeoutMs) {
  if (!tray_ || !tray_->isVisible()) {
    return;
  }
  tray_->showMessage(title, message, QSystemTrayIcon::Information,
                     std::max(0, timeoutMs));
}

void TrayManager::onActivated(QSystemTrayIcon::ActivationReason reason) {
  if (reason == QSystemTrayIcon::Trigger ||
      reason == QSystemTrayIcon::DoubleClick) {
    emit toggleVisibilityRequested();
  }
}

}  // namespace imgsli::app::ui::managers
