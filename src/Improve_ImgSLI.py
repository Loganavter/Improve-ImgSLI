import sys
from PyQt6.QtWidgets import QApplication
from qfluentwidgets import setTheme, Theme
from image_comparison_app import ImageComparisonApp

def main():
    app = QApplication(sys.argv)
    setTheme(Theme.AUTO)
    window = ImageComparisonApp()
    window.show()
    sys.exit(app.exec())
if __name__ == '__main__':
    main()