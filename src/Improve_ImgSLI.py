import sys
from PyQt6.QtWidgets import QApplication
from image_comparison_app import ImageComparisonApp 

def main(): 
    app = QApplication(sys.argv)
    ex = ImageComparisonApp()
    ex.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main() 
