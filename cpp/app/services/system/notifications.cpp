#include "services/system/notifications.h"

#include "utils/resource_loader.h"

#include <QFileInfo>
#include <QProcess>
#include <QStandardPaths>

namespace imgsli::app::services::system {

namespace {

bool isLinux() {
#if defined(Q_OS_LINUX)
  return true;
#else
  return false;
#endif
}

bool isFlatpak() {
  return !qEnvironmentVariableIsEmpty("FLATPAK_ID") ||
         QFileInfo::exists(QStringLiteral("/.flatpak-info"));
}

}  // namespace

NotificationService::NotificationService(QString appName, QString appIconPath)
    : appName_(std::move(appName)), appIconPath_(std::move(appIconPath)) {
  if (appIconPath_.isEmpty()) {
    appIconPath_ = utils::resourcePath(QStringLiteral("assets/icons/icon.png"));
  }
}

void NotificationService::setTrayIcon(QSystemTrayIcon* tray) { tray_ = tray; }

bool NotificationService::send(const QString& title, const QString& message,
                               const QString& imagePath, int timeoutMs) {
  if (!enabled_) {
    return false;
  }
  if (isLinux() && !isFlatpak()) {
    if (sendViaNotifySend(title, message, imagePath, timeoutMs)) {
      return true;
    }
  }
  return sendViaTray(title, message, timeoutMs);
}

bool NotificationService::sendViaNotifySend(const QString& title,
                                            const QString& message,
                                            const QString& imagePath,
                                            int timeoutMs) {
  const QString program = QStandardPaths::findExecutable(QStringLiteral("notify-send"));
  if (program.isEmpty()) {
    return false;
  }
  QStringList args;
  args << QStringLiteral("--app-name") << appName_
       << QStringLiteral("-t") << QString::number(std::max(0, timeoutMs));
  QString icon;
  if (!imagePath.isEmpty() && QFileInfo::exists(imagePath)) {
    icon = imagePath;
  } else if (QFileInfo::exists(appIconPath_)) {
    icon = appIconPath_;
  }
  if (!icon.isEmpty()) {
    args << QStringLiteral("-i") << icon;
  }
  args << title << message;
  return QProcess::startDetached(program, args);
}

bool NotificationService::sendViaTray(const QString& title, const QString& message,
                                      int timeoutMs) {
  if (!tray_ || !tray_->isVisible()) {
    return false;
  }
  tray_->showMessage(title, message, QSystemTrayIcon::Information,
                     std::max(0, timeoutMs));
  return true;
}

}  // namespace imgsli::app::services::system
