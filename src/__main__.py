import argparse
import logging
import os
import sys
from pathlib import Path

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
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, application_path)

# Must run before any code that writes to stderr (windowed builds set it to None).
from core.windowed_stdio import enable_faulthandler, ensure_stdio

ensure_stdio()
enable_faulthandler()

from PySide6.QtCore import QLoggingCategory, QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QApplication
from core.runtime_flags import RuntimeFlags
from plugins.settings.manager import SettingsManager
from sli_ui_toolkit.widgets import install_application_tooltips
from ui.main_window import MainWindow
from ui.widgets.canvas.rhi_backend import (
    configure_rhi_process_environment,
    configure_vulkan_layer_environment,
    persist_rhi_backend_setting,
    requested_rhi_backend_name,
    resolve_rhi_backend_with_fallback,
    supported_rhi_backend_names,
)

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
    merged_rules = ";".join(merged)
    if merged_rules:
        os.environ["QT_LOGGING_RULES"] = merged_rules
        try:
            QLoggingCategory.setFilterRules(merged_rules)
        except Exception:
            pass

def _configure_linux_desktop_integrations() -> None:
    if os.name != "posix":
        return

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

def main():
    parser = argparse.ArgumentParser(description="Improve ImgSLI - Main entry point")
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
        "--rhi-backend",
        choices=supported_rhi_backend_names(),
        default=None,
        help="Select the QRhi backend for every render widget in the process.",
    )

    args = parser.parse_args()

    # Backend resolution order: CLI flag > QSettings > env var > "default".
    # QSettings is consulted before QApplication exists; that's safe (QSettings
    # uses platform-native config, no QApp required).
    selected_rhi_backend = args.rhi_backend
    if selected_rhi_backend is None:
        try:
            from PySide6.QtCore import QSettings
            qs = QSettings("improve-imgsli", "improve-imgsli")
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
        settings_manager = SettingsManager("improve-imgsli", "improve-imgsli")

        if args.enable_logging:
            settings_manager._save_setting("debug_mode_enabled", True)
        elif args.disable_logging:
            settings_manager._save_setting("debug_mode_enabled", False)
        sys.exit(0)

    argv = sys.argv[:]
    if os.name == "posix" and not getattr(sys, "frozen", False):
        argv[0] = "improve-imgsli"
    app = QApplication(argv)

    # Probe after QApplication exists. Vulkan instance create needs a GUI app;
    # fall back before any QRhiWidget is constructed.
    effective_rhi, rhi_fallback_reason = resolve_rhi_backend_with_fallback(
        selected_rhi_backend
    )
    if rhi_fallback_reason:
        logging.getLogger("ImproveImgSLI.rhi").warning(
            "%s (requested=%s)", rhi_fallback_reason, selected_rhi_backend
        )
        configure_rhi_process_environment(effective_rhi)
        configure_vulkan_layer_environment(effective_rhi)
        # Persist for any Auto/Vulkan request that we had to override — not only
        # the literal "vulkan" string — so the next launch skips the broken path.
        if not cli_forced_rhi and selected_rhi_backend in ("vulkan", "default"):
            persist_rhi_backend_setting(effective_rhi)
    elif effective_rhi != "default":
        configure_rhi_process_environment(effective_rhi)
        configure_vulkan_layer_environment(effective_rhi)
    logging.getLogger("ImproveImgSLI.rhi").info(
        "QRhi backend effective=%s requested=%s",
        effective_rhi,
        selected_rhi_backend,
    )

    install_application_tooltips(app)
    from shared_toolkit.ui.decorate_dialog import install_application_dialog_decorations
    install_application_dialog_decorations(app)

    app.setApplicationName("Improve ImgSLI")
    app.setApplicationDisplayName("Improve ImgSLI")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("improve-imgsli")
    app.setOrganizationDomain("improve-imgsli.local")
    app.setDesktopFileName("improve-imgsli")

    from PySide6.QtGui import QIcon
    from utils.resource_loader import resource_path
    app.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))

    runtime_flags = RuntimeFlags(
        debug=bool(args.debug or args.ui_inspector),
        ui_inspector=bool(args.ui_inspector),
    )
    window = MainWindow(runtime_flags=runtime_flags)
    window.start()

    def on_quit():
        QThreadPool.globalInstance().clear()

    app.aboutToQuit.connect(on_quit)
    _install_sigint_quit(app)
    exit_code = app.exec()
    try:
        logging.shutdown()
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
