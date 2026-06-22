#pragma once

#include <QPointer>
#include <QString>
#include <QSystemTrayIcon>

namespace imgsli::app::services::system {

// Cross-platform notification facade. On Linux it prefers `notify-send` (when
// available and not running inside Flatpak), then falls back to a tray-icon
// message bubble. On other platforms it goes straight to the tray bubble.
//
// Matches the surface of Python `services.system.notifications.NotificationService`
// minus the optional D-Bus path (left as a future enhancement).
class NotificationService {
 public:
  explicit NotificationService(QString appName = QStringLiteral("Improve-ImgSLI"),
                               QString appIconPath = {});

  void setTrayIcon(QSystemTrayIcon* tray);
  void setEnabled(bool enabled) { enabled_ = enabled; }
  bool isEnabled() const noexcept { return enabled_; }

  // Returns true if the notification was dispatched through some backend.
  bool send(const QString& title, const QString& message,
            const QString& imagePath = {}, int timeoutMs = 4000);

 private:
  bool sendViaNotifySend(const QString& title, const QString& message,
                         const QString& imagePath, int timeoutMs);
  bool sendViaTray(const QString& title, const QString& message, int timeoutMs);

  QString appName_;
  QString appIconPath_;
  bool enabled_ = true;
  QPointer<QSystemTrayIcon> tray_;
};

}  // namespace imgsli::app::services::system
