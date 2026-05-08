import logging
import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QSystemTrayIcon
try:
    from PyQt6.QtDBus import QDBusConnection, QDBusMessage, QDBusVariant

    QT_DBUS_AVAILABLE = True
except Exception:
    QDBusConnection = None
    QDBusMessage = None
    QDBusVariant = None
    QT_DBUS_AVAILABLE = False

from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

DEFAULT_APP_ID = "io.github.Loganavter.Improve-ImgSLI"

class NotificationService:

    def __init__(
        self,
        app_name: str = "Improve-ImgSLI",
        app_icon_path: Optional[str] = None,
        app_id: Optional[str] = None,
    ):
        self.app_name = app_name
        self.app_id = app_id or self._detect_app_id()

        self.app_icon_path = Path(
            app_icon_path or resource_path("resources/icons/icon.png")
        )
        self._enabled = True
        self._portal_notification_seq = 0

        self.tray_icon: Optional[QSystemTrayIcon] = None

    def _detect_app_id(self) -> str:
        flatpak_id = os.environ.get("FLATPAK_ID")
        if flatpak_id:
            return flatpak_id
        return DEFAULT_APP_ID

    def _is_linux(self) -> bool:
        return os.name == "posix"

    def _prefer_portal_notifications(self) -> bool:
        if not self._is_linux():
            return False
        if os.environ.get("FLATPAK_ID"):
            return True
        if os.path.exists("/.flatpak-info"):
            return True
        if os.environ.get("GTK_USE_PORTAL") == "1":
            return True
        return True

    def _build_portal_notification_id(self) -> str:
        self._portal_notification_seq += 1
        return f"notification-{self._portal_notification_seq}"

    def _send_via_portal(
        self,
        title: str,
        message: str,
        image_path: Optional[str] = None,
        timeout_ms: int = 4000,
    ) -> bool:
        del image_path, timeout_ms
        if not QT_DBUS_AVAILABLE or QDBusConnection is None or QDBusMessage is None or QDBusVariant is None:
            return False

        try:
            bus = QDBusConnection.sessionBus()
            if not bus.isConnected():
                return False

            notification_id = self._build_portal_notification_id()
            payload = {
                "title": QDBusVariant(title or ""),
                "body": QDBusVariant(message or ""),
                "priority": QDBusVariant("normal"),
                "display-hint": QDBusVariant(["transient"]),
            }
            if self.app_id:
                payload["icon"] = QDBusVariant(self.app_id)

            dbus_message = QDBusMessage.createMethodCall(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Notification",
                "AddNotification",
            )
            dbus_message.setArguments([self.app_id, notification_id, payload])
            reply = bus.call(dbus_message)
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                logger.warning(
                    "Portal notification failed: %s",
                    reply.errorMessage(),
                )
                return False
            return True
        except Exception as exc:
            logger.error("Portal notification failed: %s", exc)
            return False

    def set_tray_icon(self, tray_icon: Optional[QSystemTrayIcon]):
        self.tray_icon = tray_icon

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    def send(
        self,
        title: str,
        message: str,
        image_path: Optional[str] = None,
        timeout_ms: int = 4000,
    ) -> bool:
        """
        Отправляет системное уведомление.
        Возвращает True, если уведомление было отправлено хотя бы одним способом.
        """
        if not self._enabled:
            return False

        if self._prefer_portal_notifications():
            try:
                if self._send_via_portal(title, message, image_path, timeout_ms):
                    return True
            except Exception as e:
                logger.error(f"Ошибка отправки через portal: {e}")

        if self._is_linux():
            return False

        try:
            if self.tray_icon and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    max(0, int(timeout_ms)),
                )
                return True
        except Exception as e:
            logger.error(f"Ошибка уведомления через трей (fallback): {e}")

        return False

    def shutdown(self):
        logger.debug("Начало остановки NotificationService...")
        logger.debug("NotificationService остановлен.")
