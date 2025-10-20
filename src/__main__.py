import argparse
import os
import sys
from pathlib import Path

try:

    current_dir = Path(__file__).resolve().parent

    project_dir = current_dir.parent

    if str(project_dir) not in sys.path:
        sys.path.insert(0, str(project_dir))
except Exception:

    pass

if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, application_path)

from PyQt6.QtWidgets import QApplication

from core.settings import SettingsManager
from ui.main_window import ImageComparisonApp

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

    args = parser.parse_args()

    if args.enable_logging or args.disable_logging:
        app_instance = QApplication.instance()
        if not app_instance:
            app_instance = QApplication(sys.argv)
        settings_manager = SettingsManager("improve-imgsli", "improve-imgsli")

        if args.enable_logging:
            settings_manager._save_setting("debug_mode_enabled", True)
            print("Debug logging has been permanently enabled.")
        elif args.disable_logging:
            settings_manager._save_setting("debug_mode_enabled", False)
            print("Debug logging has been permanently disabled.")
        sys.exit(0)

    app = QApplication(sys.argv)

    window = ImageComparisonApp(debug_mode=args.debug)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
