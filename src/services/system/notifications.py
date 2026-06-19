import logging
import os
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QSystemTrayIcon

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

    def _is_flatpak(self) -> bool:
        return bool(os.environ.get("FLATPAK_ID") or os.path.exists("/.flatpak-info"))

    def _send_via_dbus(
        self,
        title: str,
        message: str,
        image_path: Optional[str] = None,
        timeout_ms: int = 4000,
    ) -> bool:
        try:
            import dbus

            bus = dbus.SessionBus()
            notify_iface = dbus.Interface(
                bus.get_object(
                    "org.freedesktop.Notifications",
                    "/org/freedesktop/Notifications",
                ),
                "org.freedesktop.Notifications",
            )

            hints = {}
            preview_path = None
            if image_path and Path(image_path).is_file():
                preview_path = str(image_path)
                hints["image-path"] = dbus.String(preview_path)

            icon_str = preview_path
            if not icon_str:
                icon_str = (
                    str(self.app_icon_path)
                    if self.app_icon_path.is_file()
                    else self.app_name
                )

            notify_iface.Notify(
                self.app_name,
                dbus.UInt32(0),
                icon_str,
                title or "",
                message or "",
                dbus.Array([], signature="s"),
                dbus.Dictionary(hints, signature="sv"),
                dbus.Int32(timeout_ms),
            )
            return True
        except ImportError:
            logger.debug("python-dbus not available")
            return False
        except Exception as exc:
            logger.debug("D-Bus notification failed: %s", exc)
            return False

    def _send_via_notify_send(
        self,
        title: str,
        message: str,
        image_path: Optional[str] = None,
        timeout_ms: int = 4000,
    ) -> bool:
        import shutil
        import subprocess

        notify_send = shutil.which("notify-send")
        if not notify_send:
            return False

        try:
            cmd = [
                notify_send,
                "--app-name", self.app_name,
                "-t", str(max(0, int(timeout_ms))),
            ]

            icon = None
            if image_path and Path(image_path).is_file():
                icon = image_path
            elif self.app_icon_path.is_file():
                icon = str(self.app_icon_path)
            if icon:
                cmd.extend(["-i", icon])
            cmd.extend([title or "", message or ""])
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as exc:
            logger.error("notify-send failed: %s", exc)
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
        if not self._enabled:
            return False

        if self._is_linux():

            try:
                if self._send_via_dbus(title, message, image_path, timeout_ms):
                    return True
            except Exception as e:
                logger.debug("D-Bus notification error: %s", e)

            if not self._is_flatpak():
                try:
                    if self._send_via_notify_send(title, message, image_path, timeout_ms):
                        return True
                except Exception as e:
                    logger.debug("notify-send error: %s", e)

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
            logger.error("Tray notification error: %s", e)

        return False

    def shutdown(self):
        pass
