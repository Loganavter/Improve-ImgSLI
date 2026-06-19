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

from PyQt6.QtCore import QLoggingCategory, QThreadPool, Qt
from PyQt6.QtWidgets import QApplication
from core.runtime_flags import RuntimeFlags
from plugins.settings.manager import SettingsManager
from sli_ui_toolkit.widgets import install_application_tooltips
from ui.main_window import MainWindow

def _configure_qt_logging() -> None:
    current_rules = os.environ.get("QT_LOGGING_RULES", "").strip()
    extra_rules = [
        "qt.qpa.wayland.warning=false",
        "qt.qpa.services.warning=false",
    ]
    merged_rules = "\n".join(
        rule for rule in [current_rules, *extra_rules] if rule
    )
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

    args = parser.parse_args()
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
    install_application_tooltips(app)

    app.setApplicationName("Improve ImgSLI")
    app.setApplicationDisplayName("Improve ImgSLI")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("improve-imgsli")
    app.setOrganizationDomain("improve-imgsli.local")
    app.setDesktopFileName("improve-imgsli")

    from PyQt6.QtGui import QIcon
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
    exit_code = app.exec()
    try:
        logging.shutdown()
    except Exception:
        pass
    os._exit(int(exit_code) if isinstance(exit_code, int) else 0)

if __name__ == "__main__":
    main()
