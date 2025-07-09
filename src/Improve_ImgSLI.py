import sys
import argparse
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import setTheme, Theme
from image_comparison_app import ImageComparisonApp
from services.settings_manager import SettingsManager

def main():
    # 1. Определяем ВСЕ возможные аргументы
    parser = argparse.ArgumentParser(description="Improve ImgSLI - Main entry point")
    parser.add_argument('--enable-logging', action='store_true', help='Permanently enable debug logging and exit.')
    parser.add_argument('--disable-logging', action='store_true', help='Permanently disable debug logging and exit.')
    parser.add_argument('--debug', action='store_true', help='Temporarily enable debug logging for this session.')
    
    args = parser.parse_args()

    # 2. Проверяем, нужно ли выполнить сервисную команду (изменить настройку и выйти)
    if args.enable_logging or args.disable_logging:
        # Для работы QSettings нужно временное приложение
        app = QApplication.instance() or QApplication(sys.argv)
        settings_manager = SettingsManager("MyCompany", "ImageComparisonApp")
        
        if args.enable_logging:
            settings_manager._save_setting('debug_mode_enabled', True)
            print("Debug logging has been permanently enabled.")
        elif args.disable_logging:
            settings_manager._save_setting('debug_mode_enabled', False)
            print("Debug logging has been permanently disabled.")
        
        # Важно: выходим из скрипта, не запуская GUI
        sys.exit(0)

    # 3. Если сервисных команд не было, запускаем GUI
    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)
    
    # Передаем в конструктор, включен ли временный режим отладки
    window = ImageComparisonApp(debug_mode=args.debug)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()