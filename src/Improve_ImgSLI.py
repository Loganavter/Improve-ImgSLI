import sys
from PyQt6.QtWidgets import QApplication
# Убедитесь, что этот импорт правильный
from .image_comparison_app import ImageComparisonApp # Добавили точку

def main(): # <--- Добавили эту функцию
    app = QApplication(sys.argv)
    ex = ImageComparisonApp()
    ex.show()
    sys.exit(app.exec())

# Теперь вызываем main() здесь:
if __name__ == '__main__':
    main() # <--- Вызов функции