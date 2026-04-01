from __future__ import annotations

import logging
import weakref

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

logger = logging.getLogger("ImproveImgSLI")

class UIResourceManager(QObject):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        self._entries: dict[int, dict] = {}

    @property
    def host(self) -> QWidget:
        return self._host

    def register(
        self,
        obj: QObject | None,
        *,
        name: str = "",
        hide: bool = False,
        close: bool = False,
        delete: bool = False,
        stop: bool = False,
    ):
        if obj is None:
            return None

        obj_id = id(obj)
        self._entries[obj_id] = {
            "ref": weakref.ref(obj),
            "name": name or type(obj).__name__,
            "hide": bool(hide),
            "close": bool(close),
            "delete": bool(delete),
            "stop": bool(stop),
        }

        try:
            obj.destroyed.connect(lambda *_args, key=obj_id: self._entries.pop(key, None))
        except Exception:
            pass
        return obj

    def register_widget(self, widget: QWidget | None, *, name: str = "", delete: bool = True):
        return self.register(
            widget,
            name=name,
            hide=True,
            close=True,
            delete=delete,
        )

    def register_menu(self, menu: QMenu | None, *, name: str = "", delete: bool = True):
        return self.register(
            menu,
            name=name,
            hide=True,
            close=True,
            delete=delete,
        )

    def register_timer(self, timer: QTimer | None, *, name: str = ""):
        return self.register(timer, name=name, stop=True)

    def shutdown(self) -> None:
        for meta in list(self._entries.values()):
            obj = meta["ref"]()
            if obj is None:
                continue

            if meta["stop"] and isinstance(obj, QTimer):
                try:
                    obj.stop()
                except Exception:
                    pass

            if meta["hide"] and hasattr(obj, "hide"):
                try:
                    obj.hide()
                except Exception:
                    pass

            if meta["close"] and hasattr(obj, "close"):
                try:
                    obj.close()
                except Exception:
                    pass

            if meta["delete"] and hasattr(obj, "deleteLater"):
                try:
                    obj.deleteLater()
                except Exception:
                    pass

        app = QApplication.instance()
        if app is not None:
            try:
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
            except Exception:
                pass

    def debug_dump(self, stage: str = "dump") -> None:
        app = QApplication.instance()
        logger.debug("[UIResourceManager] stage=%s registered=%d", stage, len(self._entries))
        for meta in list(self._entries.values()):
            obj = meta["ref"]()
            if obj is None:
                continue
            try:
                logger.debug(
                    "[UIResourceManager] stage=%s name=%s type=%s visible=%s parent=%r",
                    stage,
                    meta["name"],
                    type(obj).__name__,
                    obj.isVisible() if hasattr(obj, "isVisible") else None,
                    obj.parent(),
                )
            except Exception:
                logger.debug(
                    "[UIResourceManager] stage=%s name=%s type=%s",
                    stage,
                    meta["name"],
                    type(obj).__name__,
                )

        if app is not None:
            try:
                top_levels = list(app.topLevelWidgets())
                logger.debug(
                    "[UIResourceManager] stage=%s top_levels=%d",
                    stage,
                    len(top_levels),
                )
                for widget in top_levels:
                    if widget is None:
                        continue
                    logger.debug(
                        "[UIResourceManager] stage=%s top_level type=%s visible=%s name=%s title=%s parent=%r",
                        stage,
                        type(widget).__name__,
                        widget.isVisible(),
                        widget.objectName(),
                        widget.windowTitle(),
                        widget.parent(),
                    )
            except Exception:
                pass
