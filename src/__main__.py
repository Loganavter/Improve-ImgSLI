import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Audit-Meta: pattern=single-owner reason="startup composition: CLI parse, backend fallback, logging/theme bootstrap and the run loop in one readable sequence; the watchdog hook is one line here on purpose"
try:
    current_dir = Path(__file__).resolve().parent
    project_dir = current_dir.parent
    bundled_src_dir = current_dir / "src"

    if str(project_dir) not in sys.path:
        sys.path.insert(0, str(project_dir))
    if bundled_src_dir.is_dir() and str(bundled_src_dir) not in sys.path:
        sys.path.insert(0, str(bundled_src_dir))
except Exception:
    pass

if getattr(sys, "frozen", False):
    application_path = sys._MEIPASS  # type: ignore[attr-defined]  # PyInstaller-only
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, application_path)

# Must run before any code that writes to stderr (windowed builds set it to None).
from core.windowed_stdio import enable_faulthandler, ensure_stdio

ensure_stdio()
_FAULT_DUMP_FILE = enable_faulthandler()

#: The previous session's marker (``plugins.diagnostics.session_marker``) and the
#: module that wrote/reads it, resolved in :func:`_begin_session_marker`.
_PREVIOUS_SESSION = None
_SESSION_MARKER = None


# Early startup sink (see core/startup_early_log.py): everything below until
# `core.bootstrap._configure_logging` runs has no log handler yet, so a plain
# logger line would be dropped (and a windowed build's stderr is os.devnull).
# The import is stdlib-only and its import time is the sink's +0 ms origin, so
# `main.entry` here is the first line of startup_early.log -- the marks that
# used to be invisible, not absent. Both calls are no-ops unless
# IMGSLI_STARTUP_TRACE / IMGSLI_STALL_WATCH (or BLINKTABLE_* spellings) is on.
try:
    from core.startup_trace import early_mark, startup_mark
except Exception:  # startup diagnostics must never block startup

    def startup_mark(phase: str) -> None:
        return None

    def early_mark(name: str, **_fields: object) -> None:
        return None


startup_mark("main.entry")
early_mark("main.entry")


from PySide6.QtCore import QLoggingCategory, QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QApplication
from core.runtime_flags import RuntimeFlags
from plugins.settings.manager import SettingsManager
from shared.debug_flags import env_flag
from sli_ui_toolkit.widgets import install_application_tooltips
from ui.main_window import MainWindow
from ui.canvas_infra.rhi.rhi_backend import (
    configure_rhi_process_environment,
    configure_vulkan_layer_environment,
    persist_rhi_backend_setting,
    record_rhi_fallback_notice,
    requested_rhi_backend_name,
    resolve_rhi_backend_with_fallback,
    supported_rhi_backend_names,
)
from core.log_names import APP_LOGGER_NAME

# End of the module-scope import block: `main.entry` to here is the import cost
# (PySide6 + toolkit + the whole ui/plugins tree) that no other probe wrapped.
early_mark("main.imports_done")

def _configure_qt_logging() -> None:
    current_rules = os.environ.get("QT_LOGGING_RULES", "").strip()
    # QT_LOGGING_RULES uses ';' (or spaces). Newlines are treated as one
    # malformed rule and Qt prints "Ignoring malformed logging rule".
    extra_rules = [
        "qt.qpa.wayland.warning=false",
        "qt.qpa.services.warning=false",
    ]
    parts: list[str] = []
    if current_rules:
        parts.extend(
            piece.strip()
            for piece in current_rules.replace("\n", ";").split(";")
            if piece.strip()
        )
    parts.extend(extra_rules)
    # De-dupe while preserving order.
    merged: list[str] = []
    seen: set[str] = set()
    for rule in parts:
        if rule in seen:
            continue
        seen.add(rule)
        merged.append(rule)
    # Env var accepts ';'; setFilterRules on some Qt builds treats ';' as
    # part of a single rule and warns "Ignoring malformed logging rule".
    env_rules = ";".join(merged)
    filter_rules = "\n".join(merged)
    if env_rules:
        os.environ["QT_LOGGING_RULES"] = env_rules
        try:
            QLoggingCategory.setFilterRules(filter_rules)
        except Exception:
            pass

def _configure_linux_desktop_integrations() -> None:
    if os.name != "posix":
        return

    # NOT the product name: this X11/Wayland WM_CLASS must keep matching the
    # desktop entry that launcher.py installs (its StartupWMClass line pins
    # the same id), so the taskbar keeps grouping the window with its icon.
    # Rename both sides together, never this one alone.
    os.environ.setdefault("RESOURCE_NAME", "improve-imgsli")

    os.environ.setdefault("UBUNTU_MENUPROXY", "0")
    try:
        QApplication.setAttribute(
            Qt.ApplicationAttribute.AA_DontUseNativeMenuBar,
            True,
        )
    except Exception:
        pass

def _install_sigint_quit(app: QApplication) -> None:
    """Make Ctrl+C quit the Qt event loop without a KeyboardInterrupt traceback.

    Python only delivers SIGINT between bytecode instructions. While Qt blocks
    in C++, the default handler never runs until some Python code wakes up —
    often inside ``eventFilter``, which then prints a noisy traceback. A short
    wake timer lets the signal handler call ``app.quit()`` cleanly.
    """
    import signal

    signal.signal(signal.SIGINT, lambda *_args: app.quit())
    wake = QTimer(app)
    wake.setInterval(200)
    wake.timeout.connect(lambda: None)
    wake.start()


def _startup_dump_delay_ms(args: argparse.Namespace) -> int:
    """Settle delay before a startup dump fires.

    Tab actions register when their tab is created, and dialog/panel layout
    settles over a few event-loop turns; both need longer than the plain
    banner-only dump. Shared by ``--dump-ui-layout`` and
    ``--dump-app-snapshot`` so the two devtools agree on timing.
    """
    return 600 if (args.open_tab or args.run_action) else 300


#: Diagnostic-only cold-launch A/B knob. The protocol, the probe and the
#: inert-by-default guarantee live with the cold-start tests
#: (``tests/runtime/test_csd_menu_width_cold_start.py``).
_FONT_PREWARM_ENV = "IMGSLI_FONT_PREWARM"


def _font_prewarm_requested() -> bool:
    """True only when ``IMGSLI_FONT_PREWARM`` holds a truthy value.

    Uses the app's permissive flag reader, so ``1``/``yes``/``on``/``true``
    (or the ``BLINKTABLE_`` spelling) are on and ``0``/``false``/``no``/``off``
    or an unset/empty value are off — the same vocabulary as every other
    diagnostic env knob.
    """
    return env_flag(_FONT_PREWARM_ENV)


def _prewarm_font_metrics() -> tuple[float, str] | None:
    """Pay the first font advance here; return ``(cost_ms, font family)``.

    The first ``horizontalAdvance`` of a fresh process is where a cold launch
    pays the one-time font-engine init (26-54 ms on the recon host; the
    owner's Windows build blocks 2.9-5.7 s on that same first advance, inside
    the CSD menu trigger width estimator). Returning the family too lets an
    A/B run compare this face with the one the title bar later measures — a
    warm-up on a different face would not cover the stall.

    ``None`` when the warm-up cannot run (import or font lookup failure); the
    caller reports that instead of claiming a zero cost.
    """
    started = time.perf_counter()
    try:
        from PySide6.QtGui import QFontMetrics

        from sli_ui_toolkit.ui.managers.ui_font import ui_font

        font = ui_font()
        QFontMetrics(font).horizontalAdvance("Aa")
        family = str(font.family())
    except Exception:
        return None
    return (time.perf_counter() - started) * 1000.0, family


def _maybe_prewarm_font_metrics() -> None:
    """Run the env-gated pre-warm and record its cost in the startup trace.

    Inert by default: with ``IMGSLI_FONT_PREWARM`` unset this returns before
    any work — no Qt call, no mark, no behaviour change. When on, the cost
    lands in the *early* startup file (``startup_early.log``): this runs a
    couple of lines after ``QApplication``, long before ``core.bootstrap``
    configures logging, so ``early_mark`` (the existing pre-log sink; the same
    one that carries ``main.qapp_ready`` right next to it) is the only
    channel. A run therefore needs ``IMGSLI_STARTUP_TRACE=1`` for the file to
    be open at all.
    """
    if not _font_prewarm_requested():
        return
    result = _prewarm_font_metrics()
    if result is None:
        early_mark("font.prewarm.failed")
        return
    cost_ms, family = result
    early_mark("font.prewarm", cost_ms=f"{cost_ms:.1f}", family=family)



def _begin_session_marker() -> None:
    """Claim this session, after reading what the PREVIOUS one left behind.

    A normal exit rewrites the marker as clean; anything else (task-manager kill,
    power cut, segfault, a startup that died) leaves ``clean: false`` and the next
    start offers a diagnostics report. Called first thing in :func:`main`, so a
    startup that fails later still left its marker.

    Never raises: a crash DETECTOR must not be able to break startup.
    """
    global _PREVIOUS_SESSION, _SESSION_MARKER
    try:
        from plugins.diagnostics import session_marker

        log_file = ""
        try:
            from core.log_names import APP_LOGGER_NAME
            from sli_ui_toolkit.core.logging import get_log_directory

            log_file = str(Path(get_log_directory(APP_LOGGER_NAME)) / "log.txt")
        except Exception:
            log_file = ""
        version = ""
        try:
            from core.constants import AppConstants

            version = str(AppConstants.APP_VERSION)
        except Exception:
            version = ""
        _SESSION_MARKER = session_marker
        _PREVIOUS_SESSION = session_marker.read_previous()
        session_marker.begin_session(
            log_file=log_file,
            fault_file=_FAULT_DUMP_FILE or "",
            version=version,
        )
    except Exception:  # noqa: BLE001 - see the docstring
        _SESSION_MARKER = None
        _PREVIOUS_SESSION = None


def main():
    _begin_session_marker()
    parser = argparse.ArgumentParser(description="BlinkTable - Main entry point")
    parser.add_argument(
        "--enable-logging",
        action="store_true",
        help="Permanently enable debug logging and exit.",
    )
    parser.add_argument(
        "--disable-logging",
        action="store_true",
        help="Permanently disable debug logging and exit.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Temporarily enable debug logging for this session.",
    )
    parser.add_argument(
        "--ui-inspector",
        action="store_true",
        help="Enable the developer UI inspector for this session.",
    )
    parser.add_argument(
        "--dump-ui-layout",
        metavar="PATH",
        default=None,
        help="Dump the live widget tree (geometry + per-widget colors + bound "
        "Find Action ids) to "
        "PATH as JSON after startup, then exit. PATH is any writable file "
        "path, e.g. /tmp/layout.json (parent dir must exist; overwrites if "
        "present). Startup lands on the Session Picker, so tab actions "
        "(image_compare.*, multi_compare.*) are only in the dump unless you "
        "also pass --open-tab (or a project to open).",
    )
    parser.add_argument(
        "--dump-app-snapshot",
        metavar="PATH",
        default=None,
        help="Dump the live ActionRegistry catalog + Redux Store slices "
        "(settings, workspace sessions, active document summary) to PATH as "
        "JSON after startup, then exit. Same startup-timing rules as "
        "--dump-ui-layout: pass --open-tab to give tab actions a chance to "
        "register first. Read-only devtool surface for the MCP server "
        "(see docs/dev/MCP.md).",
    )
    parser.add_argument(
        "--open-tab",
        metavar="TAB_KIND",
        default=None,
        help="Create and switch to a new tab of this type on startup (before "
        "--dump-ui-layout runs, if given), e.g. image_compare or "
        "multi_compare — any kind with a registered 'workspace.new_TAB_KIND' "
        "action (see docs/dev/ACTIONS.md). Lets you dump a tab's own chrome "
        "instead of the Session Picker's, without needing an existing "
        "project file. Unknown kinds are logged and ignored.",
    )
    parser.add_argument(
        "--run-action",
        metavar="ACTION_ID",
        action="append",
        default=[],
        help="Run this Find Action id (see docs/dev/ACTIONS.md / "
        "ActionRegistry) on startup, e.g. platform.settings or platform.help "
        "— opens that dialog so --dump-ui-layout can capture it too (only "
        "MainWindow is captured otherwise; --dump-ui-layout now walks every "
        "top-level window). Repeatable; runs in order, after --open-tab. "
        "Unknown ids are logged and ignored.",
    )
    parser.add_argument(
        "--rhi-backend",
        choices=supported_rhi_backend_names(),
        default=None,
        help="Select the QRhi backend for every render widget in the process.",
    )
    parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help="Optional portable .blinktable project to open after startup.",
    )
    parser.add_argument(
        "--register-file-types",
        action="store_true",
        help="On Windows, (re)register project file associations in HKCU and exit.",
    )

    args = parser.parse_args()

    if args.register_file_types:
        from services.system.windows_file_association import (
            register_project_file_association,
        )

        ok = register_project_file_association(force=True)
        sys.exit(0 if ok or sys.platform != "win32" else 1)

    # Backend resolution order: CLI flag > QSettings > env var > "default".
    # QSettings is consulted before QApplication exists; that's safe (QSettings
    # uses platform-native config, no QApp required).
    selected_rhi_backend = args.rhi_backend
    if selected_rhi_backend is None:
        try:
            from core.plugin_system.settings import canonical_settings

            qs = canonical_settings()
            saved = str(qs.value("rhi_backend", "") or "").strip().lower()
            if saved and saved in supported_rhi_backend_names():
                selected_rhi_backend = saved
        except Exception:
            pass
    if not selected_rhi_backend:
        selected_rhi_backend = requested_rhi_backend_name()
    cli_forced_rhi = args.rhi_backend is not None
    if selected_rhi_backend != "default":
        configure_rhi_process_environment(selected_rhi_backend)
    configure_vulkan_layer_environment(selected_rhi_backend)
    _configure_qt_logging()
    _configure_linux_desktop_integrations()

    if args.enable_logging or args.disable_logging:
        app_instance = QApplication.instance()
        if not app_instance:
            app_instance = QApplication(sys.argv)
        from core.plugin_system.settings import SETTINGS_APP, SETTINGS_ORG

        settings_manager = SettingsManager(SETTINGS_ORG, SETTINGS_APP)

        if args.enable_logging:
            settings_manager._save_setting("debug_mode_enabled", True)
        elif args.disable_logging:
            settings_manager._save_setting("debug_mode_enabled", False)
        sys.exit(0)

    argv = sys.argv[:]
    if os.name == "posix" and not getattr(sys, "frozen", False):
        # Kept on the pre-rename spelling on purpose: argv[0] feeds the same
        # WM_CLASS as ``RESOURCE_NAME`` above (see that comment — the desktop
        # entry is the other half of the pair).
        argv[0] = "improve-imgsli"
    app = QApplication(argv)
    early_mark("main.qapp_ready")

    # Cold-launch A/B (IMGSLI_FONT_PREWARM=1, diagnostic only): pay the
    # one-time font-engine init here — after QApplication (needs the platform
    # font database), before the RHI probe and MainWindow — so one run says
    # whether the 3-4 s title-bar stall is that init or the trigger
    # measurements that currently trigger it. Inert with the env unset: no
    # call, no mark, no behaviour change.
    _maybe_prewarm_font_metrics()

    # Project-wide widget substitution (toolkit scrollbar policy): every
    # stock scroll area gets MinimalistScrollBar bars at polish time, so no
    # call site can silently reintroduce the native look. Fail-open: a
    # broken policy must never block startup.
    try:
        from sli_ui_toolkit.widgets import install_scrollbar_policy

        install_scrollbar_policy(app)
    except Exception:
        pass

    # GUI-thread stall watchdog (diagnosis only, IMGSLI_STALL_WATCH=1): a
    # hitch deferred past the action that caused it (queued slot, debounce
    # flush, GC, lazy cache) has no probe around the action -- this one names
    # the blocking stack instead.
    try:
        from core.stall_watch import arm as _arm_stall_watch

        _arm_stall_watch()
    except Exception:
        pass
    # Test hook (off unless IMGSLI_STARTUP_EARLY_SELFTEST_SLEEP_MS is set):
    # holds the GUI thread while the watchdog is armed and no log handler
    # exists yet, so a deliberate [stall] proves the early sink catches it.
    try:
        from core.startup_early_log import selftest_sleep as _early_selftest_sleep

        _early_selftest_sleep()
    except Exception:
        pass

    # Probe after QApplication exists. Vulkan instance create needs a GUI app;
    # fall back before any QRhiWidget is constructed. The probe is the slowest
    # pre-window step (307-374 ms cold on D3D11) and it blocks the GUI thread,
    # so its cost and any watchdog report belong in the early startup file.
    early_mark("rhi.probe.start", requested=selected_rhi_backend)
    effective_rhi, rhi_fallback_reason = resolve_rhi_backend_with_fallback(
        selected_rhi_backend
    )
    early_mark("rhi.probe.end", effective=effective_rhi)
    if rhi_fallback_reason:
        logging.getLogger(f"{APP_LOGGER_NAME}.rhi").warning(
            "%s (requested=%s)", rhi_fallback_reason, selected_rhi_backend
        )
        configure_rhi_process_environment(effective_rhi)
        configure_vulkan_layer_environment(effective_rhi)
        record_rhi_fallback_notice(
            selected_rhi_backend, effective_rhi, rhi_fallback_reason
        )
        # Sticky-persist only an explicit Vulkan/OpenGL failure onto a *working*
        # alternative. Never rewrite Auto from a probe, and never persist Null.
        if (
            not cli_forced_rhi
            and selected_rhi_backend in ("vulkan", "opengl", "d3d11", "d3d12", "metal")
            and effective_rhi not in ("null", "default", selected_rhi_backend)
        ):
            persist_rhi_backend_setting(effective_rhi)
    elif effective_rhi != "default":
        configure_rhi_process_environment(effective_rhi)
        configure_vulkan_layer_environment(effective_rhi)
    logging.getLogger(f"{APP_LOGGER_NAME}.rhi").info(
        "QRhi backend effective=%s requested=%s",
        effective_rhi,
        selected_rhi_backend,
    )

    install_application_tooltips(app)
    from shared_toolkit.ui.decorate_dialog import install_application_dialog_decorations
    install_application_dialog_decorations(app)

    # The identity Qt shows and derives paths from. Renamed to the product
    # name: ``QSettings`` is unaffected (it always receives the explicit
    # canonical pair from ``core.plugin_system.settings``), but
    # ``QStandardPaths`` cache locations move with these two strings — they
    # are rebuildable caches, and the old tree is simply left behind.
    app.setApplicationName("BlinkTable")
    app.setApplicationDisplayName("BlinkTable")
    from core.constants import AppConstants

    app.setApplicationVersion(AppConstants.APP_VERSION)
    app.setOrganizationName("BlinkTable")
    app.setOrganizationDomain("blinktable.local")
    # Desktop-entry id stays on the pre-rename spelling: it must match the
    # installed desktop file name that launcher.py writes, whose
    # StartupWMClass line pins the same id as RESOURCE_NAME above.
    # Renaming it here alone would detach the window from its launcher icon.
    app.setDesktopFileName("improve-imgsli")

    from PySide6.QtGui import QIcon
    from utils.resource_loader import resource_path
    app.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))

    try:
        from services.system.windows_file_association import ensure_windows_file_association

        ensure_windows_file_association()
    except Exception:
        logging.getLogger(APP_LOGGER_NAME).debug(
            "Windows file association skipped", exc_info=True
        )

    runtime_flags = RuntimeFlags(
        debug=bool(args.debug or args.ui_inspector),
        ui_inspector=bool(args.ui_inspector),
    )
    early_mark("main.window_start")
    window = MainWindow(runtime_flags=runtime_flags)
    window.start()
    early_mark("main.window.init_done")

    # Warm heavy third-party imports off the GUI thread -- AFTER the window is
    # built. Starting the thread before `MainWindow()` made it compete with
    # window construction for the GIL: measured +150 ms (+33%) on the main
    # thread in a clone, and on a frozen build the warm thread pulls
    # scipy.stats + skimage out of the PYZ, so the contention is seconds
    # (cold-start recon, 2026-10-24). A short delay keeps the first paint clean
    # and still lands well before the first analysis use.
    try:
        from PySide6.QtCore import QTimer as _QTimer

        from core.import_warmup import start as _start_import_warmup

        _QTimer.singleShot(250, _start_import_warmup)
    except Exception:
        pass
    from ui.canvas_infra.rhi.rhi_fallback_notice import schedule_rhi_fallback_user_notice

    schedule_rhi_fallback_user_notice(window)

    from ui.main_window.cache_purge_notice import schedule_cache_purge_notice

    schedule_cache_purge_notice(
        window, getattr(window.app_context, "cache_purge_notice_bytes", None)
    )

    if args.open_tab:
        from ui.actions.registry import get_action_registry

        def _open_startup_tab(tab_kind: str = args.open_tab) -> None:
            action_id = f"workspace.new_{tab_kind}"
            action = get_action_registry().get(action_id)
            if action is not None and action.run is not None:
                action.run()
            else:
                logging.getLogger(APP_LOGGER_NAME).warning(
                    "--open-tab %s: no such action (%s not registered)",
                    tab_kind,
                    action_id,
                )

        QTimer.singleShot(0, _open_startup_tab)

    if args.run_action:
        from ui.actions.registry import get_action_registry

        def _run_startup_actions(action_ids: list[str] = args.run_action) -> None:
            registry = get_action_registry()
            for action_id in action_ids:
                action = registry.get(action_id)
                if action is not None and action.run is not None:
                    action.run()
                else:
                    logging.getLogger(APP_LOGGER_NAME).warning(
                        "--run-action %s: no such action", action_id
                    )

        # After --open-tab's singleShot(0, ...), same delay: Qt fires
        # zero-delay timers in registration order.
        QTimer.singleShot(0, _run_startup_actions)

    if args.dump_ui_layout:
        dump_path = args.dump_ui_layout

        def _dump_ui_layout_and_quit(path: str = dump_path) -> None:
            import json

            from devtools.ui_layout_dump import dump_all_windows
            from ui.actions.registry import get_action_registry

            data = dump_all_windows(get_action_registry())
            Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            app.quit()

        # Give layouts one settled event-loop turn after show() so geometry
        # isn't still the pre-resize placeholder; longer when opening a tab
        # or running actions first so their own layout/animation settles
        # before we snapshot it.
        QTimer.singleShot(_startup_dump_delay_ms(args), _dump_ui_layout_and_quit)

    if args.dump_app_snapshot:
        snapshot_path = args.dump_app_snapshot

        def _dump_app_snapshot_and_quit(path: str = snapshot_path) -> None:
            import json

            from devtools.app_snapshot import dump_snapshot
            from ui.actions.registry import get_action_registry

            data = dump_snapshot(window.store, get_action_registry())
            Path(path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            app.quit()

        # Same settle delay as --dump-ui-layout: actions register during
        # window.start() and tab activation, not before the first loop turn.
        QTimer.singleShot(_startup_dump_delay_ms(args), _dump_app_snapshot_and_quit)

    if args.project:
        project_path = str(Path(args.project).expanduser().resolve())

        def _open_startup_project(path: str = project_path) -> None:
            # Use public accessor — avoids private ``_menu_controller`` hunt (C7).
            menu = getattr(window, "menu_controller", None) or getattr(
                window, "_menu_controller", None
            )
            opener = getattr(menu, "open_project_at_path", None) if menu else None
            if callable(opener):
                opener(path)

        # Defer until after the first event-loop turn so project I/O / toasts
        # see a fully started window (double-click / MIME association path).
        QTimer.singleShot(0, _open_startup_project)

    # In-app control channel (Phase 2): env-gated, local unix socket inside the
    # private runtime dir, so the MCP server can drive THIS window instead of
    # booting throwaway processes. Fail-open — a broken channel must never
    # block startup — and torn down on quit so no socket/pointer is left.
    if env_flag("IMGSLI_CONTROL"):
        try:
            from core.control import ControlServer

            control_server = ControlServer(window=window, app=app)
            if control_server.start():
                app.aboutToQuit.connect(control_server.stop)
            else:
                logging.getLogger(APP_LOGGER_NAME).warning(
                    "IMGSLI_CONTROL=1 but the control channel could not start"
                )
        except Exception:
            logging.getLogger(APP_LOGGER_NAME).warning(
                "control channel startup failed", exc_info=True
            )

    def on_quit():
        QThreadPool.globalInstance().clear()

    app.aboutToQuit.connect(on_quit)
    _install_sigint_quit(app)
    if _SESSION_MARKER is not None and _PREVIOUS_SESSION is not None:
        try:
            if _SESSION_MARKER.classify(_PREVIOUS_SESSION) == "unclean":
                from ui.main_window.unclean_shutdown_offer import (
                    schedule_unclean_shutdown_offer,
                )

                schedule_unclean_shutdown_offer(window, _PREVIOUS_SESSION)
        except Exception:
            logging.getLogger(APP_LOGGER_NAME).debug(
                "unclean-shutdown offer not scheduled", exc_info=True
            )
    exit_code = app.exec()
    try:
        logging.shutdown()
    except Exception:
        pass
    # This process is about to leave through os._exit (below), which skips atexit
    # handlers — so the "clean exit" must be written HERE, explicitly.
    if _SESSION_MARKER is not None:
        try:
            _SESSION_MARKER.mark_clean()
        except Exception:
            pass
    os._exit(int(exit_code) if isinstance(exit_code, int) else 0)

def _write_frozen_crash_log() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    try:
        import traceback

        path = Path(sys.executable).resolve().parent / "startup_crash.log"
        path.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"Wrote crash log: {path}", file=sys.stderr)
        return path
    except Exception:
        return None


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        logging.exception("Fatal error during startup")
        try:
            import traceback

            traceback.print_exc()
        except Exception:
            pass
        _write_frozen_crash_log()
        if getattr(sys, "frozen", False):
            try:
                input("\nPress Enter to exit...")
            except Exception:
                pass
        raise