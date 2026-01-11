

import asyncio
import logging
import os
import subprocess
import threading
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import QSystemTrayIcon

try:
    from desktop_notifier import Attachment, DesktopNotifier, Icon, Urgency
    DESKTOP_NOTIFIER_AVAILABLE = True
except Exception:
    DesktopNotifier = None
    Icon = None
    Attachment = None
    Urgency = None
    DESKTOP_NOTIFIER_AVAILABLE = False

from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

class NotificationService:

    def __init__(self, app_name: str = "Improve-ImgSLI", app_icon_path: Optional[str] = None):
        self.app_name = app_name

        self.app_icon_path = Path(app_icon_path or resource_path("resources/icons/icon.png"))
        self._enabled = True

        self.notifier: Optional[DesktopNotifier] = None
        self._notifier_loop: Optional[asyncio.AbstractEventLoop] = None
        self._notifier_thread: Optional[threading.Thread] = None

        self.tray_icon: Optional[QSystemTrayIcon] = None

        self._init_notifier()

    def _init_notifier(self):
        if DESKTOP_NOTIFIER_AVAILABLE and DesktopNotifier is not None and Icon is not None:
            try:

                icon_obj = Icon(path=self.app_icon_path) if self.app_icon_path.exists() else None

                self.notifier = DesktopNotifier(
                    app_name=self.app_name,
                    app_icon=icon_obj
                )
                self._start_notifier_loop()
                logger.debug("DesktopNotifier инициализирован.")
            except Exception as e:
                logger.error(f"Не удалось инициализировать DesktopNotifier: {e}")
                self.notifier = None

    def _start_notifier_loop(self):
        if self._notifier_loop is not None:
            return
        try:
            loop = asyncio.new_event_loop()
            def _runner():
                try:
                    asyncio.set_event_loop(loop)

                    try:
                        loop.run_forever()
                    except KeyboardInterrupt:
                        pass
                    except Exception as e:
                        logger.debug(f"Ошибка в event loop: {e}")
                finally:
                    try:

                        try:
                            pending = asyncio.all_tasks(loop)
                            for task in pending:
                                task.cancel()
                        except Exception:
                            pass

                        if not loop.is_closed():
                            try:

                                loop.close()
                            except Exception:
                                pass
                    except Exception:
                        pass
            th = threading.Thread(target=_runner, name="NotifierAsyncLoop", daemon=True)
            th.start()
            self._notifier_loop = loop
            self._notifier_thread = th
            logger.debug("Event loop для DesktopNotifier запущен.")
        except Exception as e:
            logger.error(f"Не удалось запустить event loop: {e}")

    def set_tray_icon(self, tray_icon: QSystemTrayIcon):
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
        timeout_ms: int = 4000
    ) -> bool:
        """
        Отправляет системное уведомление.
        Возвращает True, если уведомление было отправлено хотя бы одним способом.
        """
        if not self._enabled:
            return False

        try:

            if self.notifier is not None and self._notifier_loop is not None:
                icon_obj = None
                attach_obj = None
                if image_path and isinstance(image_path, str):
                    path_obj = None
                    try:
                        path_abs = os.path.abspath(image_path)
                        if os.path.isfile(path_abs):
                            path_obj = Path(path_abs)
                    except Exception as e:
                        logger.warning(f"Не удалось получить абсолютный путь для уведомления: {e}")

                    if path_obj:
                        if Icon is not None:
                            icon_obj = Icon(path=path_obj)
                        if Attachment is not None:
                            attach_obj = Attachment(path=path_obj)

                timeout_seconds = max(0, int(round((timeout_ms or 0) / 1000)))
                coro = self.notifier.send(
                    title=title,
                    message=message,
                    icon=icon_obj,
                    attachment=attach_obj,
                    urgency=Urgency.Normal if Urgency is not None else None,
                    timeout=timeout_seconds,
                )
                try:
                    asyncio.run_coroutine_threadsafe(coro, self._notifier_loop)
                    return True
                except Exception as e:
                    logger.error(f"Ошибка планирования DesktopNotifier: {e}")
        except Exception as e:
            logger.error(f"Ошибка отправки через DesktopNotifier: {e}")

        try:
            if self.tray_icon and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    max(0, int(timeout_ms))
                )
                return True
        except Exception as e:
            logger.error(f"Ошибка уведомления через трей (fallback): {e}")

        try:
            notify_send = None
            for cand in ("notify-send", "/usr/bin/notify-send", "/bin/notify-send"):
                if os.path.isfile(cand) and os.access(cand, os.X_OK):
                    notify_send = cand
                    break
            if notify_send:
                cmd = [notify_send, "-a", self.app_name]
                if isinstance(timeout_ms, int) and timeout_ms > 0:
                    cmd += ["-t", str(timeout_ms)]
                if image_path and isinstance(image_path, str) and os.path.isfile(image_path):
                    cmd += ["-i", os.path.abspath(image_path)]
                else:
                    try:

                        icon_path = str(self.app_icon_path) if isinstance(self.app_icon_path, Path) else self.app_icon_path
                        cmd += ["-i", icon_path]
                    except Exception:
                        pass
                cmd += [title or "", message or ""]
                subprocess.Popen(cmd)
                return True
        except Exception as e:
            logger.error(f"Ошибка notify‑send (fallback): {e}")

        return False

    def shutdown(self):
        logger.debug("Начало остановки NotificationService...")

        loop = self._notifier_loop
        if loop is not None:
            try:

                if loop.is_running():

                    try:
                        loop.call_soon_threadsafe(loop.stop)
                    except RuntimeError:

                        pass

                    import time
                    time.sleep(0.05)

                if not loop.is_closed():
                    try:

                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()

                        if pending:
                            time.sleep(0.05)
                    except (RuntimeError, ValueError):

                        pass

                if not loop.is_closed():
                    try:

                        try:
                            loop.shutdown_asyncgens()
                        except Exception:
                            pass
                        try:
                            loop.shutdown_default_executor()
                        except Exception:
                            pass

                        loop.close()
                    except Exception as e:
                        logger.debug(f"Ошибка при закрытии event loop: {e}")
            except Exception as e:
                logger.debug(f"Ошибка при остановке event loop: {e}")

        th = self._notifier_thread
        if th is not None and th.is_alive():
            try:
                import time

                th.join(timeout=0.5)
                if th.is_alive():
                    logger.debug("Поток NotificationService не завершился вовремя, но он daemon и будет завершен автоматически")
            except Exception as e:
                logger.debug(f"Ошибка при ожидании завершения потока: {e}")

        self.notifier = None
        self._notifier_loop = None
        self._notifier_thread = None
        logger.debug("NotificationService остановлен.")
