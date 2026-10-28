"""Local-first diagnostics / crash-report plugin (bootstrap tier).

On an **unhandled** exception (``sys.excepthook`` /
``threading.excepthook``) or on demand, this plugin builds a redacted
diagnostics report and offers **Copy / Save… / Open issue**. There is no
automatic upload, no telemetry, and **no window screenshots** — the report
never leaves the machine unless the user acts on it.

Installed at the **bootstrap** tier so the hooks are live before the main
window (startup crashes are still captured). The plugin owns its handlers; it
touches no core wiring. See ``docs/dev/PLUGINS.md``.
"""

from __future__ import annotations

import faulthandler
import io
import logging
import sys
import threading
import time
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal, qInstallMessageHandler

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IControllablePlugin, IServicePlugin
from core.log_names import APP_LOGGER_NAME

from . import collect, report
from .breadcrumbs import BreadcrumbBuffer
from .logring import DEFAULT_LOGRING_CAPACITY, RingBuffer, RingBufferHandler

logger = logging.getLogger(f"{APP_LOGGER_NAME}.diagnostics")

LOGGER_NAME = APP_LOGGER_NAME
QT_MESSAGE_RING_CAPACITY = 100

# Settings included in the report (scalars only; paths are redacted anyway).
_SANITIZED_SETTING_KEYS = (
    "current_language",
    "theme",
    "ui_font_mode",
    "ui_mode",
    "ui_scale_factor",
    "debug_mode_enabled",
    "rhi_backend",
    "export_last_format",
    "export_quality",
)


class _ReportPresenter(QObject):
    """Marshals a report to the GUI thread (safe from worker threads)."""

    report_ready = Signal(object)

    def __init__(self, plugin: "DiagnosticsPlugin") -> None:
        super().__init__()
        self._plugin = plugin
        self.report_ready.connect(
            self._on_report, Qt.ConnectionType.QueuedConnection
        )

    def request(self, diagnostics: report.DiagnosticsReport) -> None:
        self.report_ready.emit(diagnostics)

    def _on_report(self, diagnostics: report.DiagnosticsReport) -> None:
        self._plugin._show_dialog(diagnostics)


@plugin(name="diagnostics", version="1.0", startup_tier="bootstrap")
class DiagnosticsPlugin(Plugin, IControllablePlugin, IServicePlugin):
    """Crash-report / diagnostics plugin."""

    capabilities = ("diagnostics",)

    def __init__(self) -> None:
        super().__init__()
        self.store: Any | None = None
        self.event_bus: Any | None = None
        self.plugin_coordinator: Any | None = None

        self.breadcrumbs = BreadcrumbBuffer()
        self.last_report: report.DiagnosticsReport | None = None

        self._started_at = time.monotonic()
        self._reporting = False
        self._hooks_installed = False
        self._qt_handler_installed = False

        self._logring: RingBufferHandler | None = None
        self._qt_ring = RingBuffer(QT_MESSAGE_RING_CAPACITY)

        self._previous_excepthook = None
        self._previous_thread_excepthook = None
        self._previous_qt_handler = None

        # Stable bound-method references so restore can compare identity.
        self._excepthook = self._handle_sys_exception
        self._thread_excepthook = self._handle_thread_exception
        self._qt_message_handler = self._on_qt_message

        self._presenter: _ReportPresenter | None = None
        self._dialog: Any | None = None
        self._action_id: str | None = None
        #: Last session's failure payload while the startup offer is up.
        self._pending_failure: dict[str, Any] | None = None
        self._offer: Any | None = None

    # -- lifecycle --------------------------------------------------------

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)
        self.plugin_coordinator = getattr(context, "plugin_coordinator", None)

        self._install_log_ring()
        self._install_excepthooks()
        self._install_qt_message_handler()
        self._install_breadcrumbs()
        self._register_action()

        # Presenter carries main-thread affinity for cross-thread dialog requests.
        try:
            self._presenter = _ReportPresenter(self)
        except Exception:
            self._presenter = None

    def shutdown(self) -> None:
        self._restore_hooks()
        self._unregister_action()
        super().shutdown()

    # -- public API -------------------------------------------------------

    def get_controller(self) -> "DiagnosticsPlugin":
        return self

    def get_service(self) -> "DiagnosticsPlugin":
        return self

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if command in ("create_report", "open_report", "report"):
            return self.create_report(*args, **kwargs)
        target = getattr(self, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Diagnostics plugin has no command '{command}'")

    def create_report(
        self, failure: dict[str, Any] | None = None, *, show: bool = True
    ) -> report.DiagnosticsReport:
        """Build a report (manual entry point) and offer it to the user."""
        self.breadcrumbs.record("manual", "diagnostics.create_report")
        diagnostics = self.build_report(failure=failure)
        self.last_report = diagnostics
        if show:
            self._schedule_dialog(diagnostics)
        return diagnostics

    def build_report(
        self, *, failure: dict[str, Any] | None = None
    ) -> report.DiagnosticsReport:
        """Assemble a report from the current runtime without GUI work."""
        runtime = {
            "python": _safe(collect.collect_runtime, {}),
            "active_tab": self._active_tab(),
            "uptime_seconds": round(time.monotonic() - self._started_at, 1),
            "settings": self._sanitized_settings(),
            "plugins": self._plugin_list(),
            "qt_messages": self._qt_ring.snapshot(),
            "thread_stacks": self._thread_stacks(),
        }
        return report.assemble(
            failure=failure,
            app=_safe(collect.collect_app_info, {}),
            environment=_safe(collect.collect_environment, {}),
            machine=_safe(collect.collect_machine, {}),
            runtime=runtime,
            breadcrumbs=self.breadcrumbs.as_dicts(),
            logs=self._snapshot_logs(),
        )

    # -- hooks: logging ---------------------------------------------------

    def _install_log_ring(self) -> None:
        if self._logring is not None:
            return
        handler = RingBufferHandler(DEFAULT_LOGRING_CAPACITY)
        try:
            logging.getLogger(LOGGER_NAME).addHandler(handler)
        except Exception:
            return
        self._logring = handler

    def _snapshot_logs(self) -> list[str]:
        if self._logring is None:
            return []
        try:
            return self._logring.snapshot()
        except Exception:
            return []

    # -- hooks: breadcrumbs -----------------------------------------------

    def _install_breadcrumbs(self) -> None:
        store = self.store
        dispatcher = None
        get_dispatcher = getattr(store, "get_dispatcher", None)
        if callable(get_dispatcher):
            try:
                dispatcher = get_dispatcher()
            except Exception:
                dispatcher = None
        if dispatcher is not None:
            self.breadcrumbs.bind_dispatcher(dispatcher)

    # -- hooks: excepthooks -----------------------------------------------

    def _install_excepthooks(self) -> None:
        if self._hooks_installed:
            return
        self._previous_excepthook = sys.excepthook
        self._previous_thread_excepthook = threading.excepthook
        sys.excepthook = self._excepthook
        threading.excepthook = self._thread_excepthook
        self._hooks_installed = True

    def _handle_sys_exception(self, exc_type, exc_value, exc_traceback) -> None:
        try:
            self._handle_exception(
                exc_type,
                exc_value,
                exc_traceback,
                source="main",
                thread_name=threading.current_thread().name,
            )
        except Exception:
            logger.exception("diagnostics: sys.excepthook failed")
        previous = self._previous_excepthook
        if previous is not None and previous is not self._excepthook:
            try:
                previous(exc_type, exc_value, exc_traceback)
            except Exception:
                pass

    def _handle_thread_exception(self, args: Any) -> None:
        try:
            thread_name = getattr(getattr(args, "thread", None), "name", None)
            self._handle_exception(
                getattr(args, "exc_type", None),
                getattr(args, "exc_value", None),
                getattr(args, "exc_traceback", None),
                source="thread",
                thread_name=thread_name,
            )
        except Exception:
            logger.exception("diagnostics: threading.excepthook failed")
        previous = self._previous_thread_excepthook
        if previous is not None and previous is not self._thread_excepthook:
            try:
                previous(args)
            except Exception:
                pass

    def _handle_exception(
        self,
        exc_type: Any,
        exc_value: Any,
        exc_traceback: Any,
        *,
        source: str,
        thread_name: str | None = None,
    ) -> None:
        # Re-entrancy guard: never build a crash report from inside one.
        if self._reporting:
            return
        self._reporting = True
        try:
            failure = report.format_failure(
                exc_type,
                exc_value,
                exc_traceback,
                source=source,
                thread_name=thread_name,
            )
            try:
                self.breadcrumbs.record(
                    "error",
                    f"{failure.get('type')}: {failure.get('message')}",
                    detail=source,
                )
            except Exception:
                pass
            diagnostics = self.build_report(failure=failure)
            self.last_report = diagnostics
            self._schedule_dialog(diagnostics)
        except Exception:
            logger.exception("diagnostics: failed to build crash report")
        finally:
            self._reporting = False

    # -- hooks: Qt messages ----------------------------------------------

    def _install_qt_message_handler(self) -> None:
        if self._qt_handler_installed:
            return
        try:
            self._previous_qt_handler = qInstallMessageHandler(
                self._qt_message_handler
            )
            self._qt_handler_installed = True
        except Exception:
            self._previous_qt_handler = None

    def _on_qt_message(self, mode: Any, context: Any, message: Any) -> None:
        try:
            from PySide6.QtCore import QtMsgType

            if mode in (
                QtMsgType.QtWarningMsg,
                QtMsgType.QtCriticalMsg,
                QtMsgType.QtFatalMsg,
            ):
                self._qt_ring.append(f"[Qt] {str(message)}")
        except Exception:
            pass
        previous = self._previous_qt_handler
        if previous is not None:
            try:
                previous(mode, context, message)
            except Exception:
                pass

    # -- previous-session offer -------------------------------------------

    def offer_unclean_shutdown(self, previous: Any) -> bool:
        """Offer a report for a session that did not exit normally.

        The startup path calls this with the marker's ``PreviousSession``; the
        decision lives in ``unclean_offer`` (file-size policy), this is the host's
        seam. Returns ``False`` when the user opted out — never raises.
        """
        from . import unclean_offer

        return unclean_offer.offer(self, previous)

    # -- dialog -----------------------------------------------------------

    def _schedule_dialog(self, diagnostics: report.DiagnosticsReport) -> None:
        from . import report_ui

        report_ui.schedule(self, diagnostics)

    def _show_dialog(self, diagnostics: report.DiagnosticsReport) -> None:
        from . import report_ui

        report_ui.show(self, diagnostics)

    def _parent_widget(self) -> Any | None:
        from . import report_ui

        return report_ui.parent_widget()

    # -- runtime context --------------------------------------------------

    def _active_tab(self) -> str | None:
        store = self.store
        get_active = getattr(store, "get_active_workspace_session", None)
        if not callable(get_active):
            return None
        try:
            session = get_active()
        except Exception:
            return None
        if session is None:
            return None
        return getattr(session, "session_type", None)

    def _sanitized_settings(self) -> dict[str, Any]:
        settings = getattr(self.store, "settings", None)
        if settings is None:
            return {}
        out: dict[str, Any] = {}
        for key in _SANITIZED_SETTING_KEYS:
            value = getattr(settings, key, None)
            if value is None or isinstance(value, (str, int, float, bool)):
                out[key] = value
        return out

    def _plugin_list(self) -> list[dict[str, Any]]:
        coordinator = self.plugin_coordinator
        all_plugins = getattr(coordinator, "all_plugins", None)
        if not callable(all_plugins):
            return []
        out: list[dict[str, Any]] = []
        try:
            for instance in all_plugins():
                meta = getattr(instance, "_plugin_meta", {}) or {}
                out.append(
                    {
                        "name": meta.get("name", type(instance).__name__),
                        "version": meta.get("version"),
                        "tier": meta.get("startup_tier"),
                    }
                )
        except Exception:
            return out
        return out

    def _thread_stacks(self) -> str | None:
        try:
            if not faulthandler.is_enabled():
                return None
            buffer = io.StringIO()
            faulthandler.dump_traceback(file=buffer, all_threads=True)
            return buffer.getvalue() or None
        except Exception:
            return None

    # -- action catalog ---------------------------------------------------

    def _register_action(self) -> None:
        try:
            from core.actions.types import ActionDescriptor
            from ui.actions.registry import get_action_registry

            descriptor = ActionDescriptor(
                action_id="diagnostics.create_report",
                label_key="diagnostics.action.create_report",
                description_key="diagnostics.action.create_report_desc",
                breadcrumb=("menu.help",),
                owner_tab=None,
                topic="diagnostics",
                run=self.create_report,
            )
            get_action_registry().register(descriptor)
            self._action_id = descriptor.action_id
        except Exception:
            self._action_id = None

    def _unregister_action(self) -> None:
        action_id = self._action_id
        if not action_id:
            return
        try:
            from ui.actions.registry import get_action_registry

            get_action_registry().unregister(action_id)
        except Exception:
            pass
        self._action_id = None

    # -- teardown ---------------------------------------------------------

    def _restore_hooks(self) -> None:
        if self._hooks_installed:
            if sys.excepthook is self._excepthook:
                sys.excepthook = self._previous_excepthook or sys.__excepthook__
            if threading.excepthook is self._thread_excepthook:
                threading.excepthook = (
                    self._previous_thread_excepthook or threading.__excepthook__
                )
            self._hooks_installed = False
        if self._qt_handler_installed:
            try:
                qInstallMessageHandler(self._previous_qt_handler)
            except Exception:
                pass
            self._qt_handler_installed = False
        if self._logring is not None:
            try:
                logging.getLogger(LOGGER_NAME).removeHandler(self._logring)
            except Exception:
                pass
            self._logring = None
        try:
            self.breadcrumbs.unbind_dispatcher()
        except Exception:
            pass


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default
