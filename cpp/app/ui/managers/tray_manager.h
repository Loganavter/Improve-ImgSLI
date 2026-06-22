#pragma once

#include <QHash>
#include <QObject>
#include <QString>
#include <QSystemTrayIcon>

class QAction;
class QMenu;

namespace imgsli::app::ui::managers {

// Mirror of Python `src/ui/managers/tray_manager.py`. Owns the system tray
// icon, its context menu (toggle window, open last file/folder, quit), the
// activation→toggle mapping, and routed Qt signals for the bootstrap layer
// to wire into the comparison shell.
class TrayManager : public QObject {
  Q_OBJECT
 public:
  explicit TrayManager(QObject* parent = nullptr,
                       QString appName = QStringLiteral("Improve-ImgSLI"));
  ~TrayManager() override;

  QSystemTrayIcon* trayIcon() const noexcept { return tray_; }
  bool isAvailable() const noexcept { return tray_ != nullptr; }

  // Toggle-action labels are filled in by the caller (the i18n layer is in
  // the bootstrap). Pass empty strings to skip the update.
  void retranslate(const QString& toggleText, const QString& openFileText,
                   const QString& openFolderText, const QString& quitText);

  // Updates the "open last file" entry — hidden when no file has been saved.
  void setLastSavedPath(const QString& path);
  QString lastSavedPath() const noexcept { return lastSavedPath_; }

  void showNotification(const QString& title, const QString& message,
                        int timeoutMs = 4000);

 signals:
  void toggleVisibilityRequested();
  void openLastFileRequested();
  void openLastFolderRequested();
  void quitRequested();

 private:
  void buildContextMenu();
  void onActivated(QSystemTrayIcon::ActivationReason reason);

  QString appName_;
  QSystemTrayIcon* tray_ = nullptr;
  QMenu* menu_ = nullptr;
  QHash<QString, QAction*> actions_;
  QString lastSavedPath_;
};

}  // namespace imgsli::app::ui::managers
