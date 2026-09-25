# Original prompt (as written, 22 October 2024 — Claude 3.5 Sonnet):
#
# напиши программы на python с интерфейсом. Можно будет загрузить две картинки,
# по середине программы будет интерактивное окно с разделителем. Но сначала надо
# приравнять по размеру меньшую картинку к большей, интерполяцией по соседним
# пикселям. Получается что в окне будет ползунок которым можно будет двигать
# мышкой, он перемещает черную вертикальную линию равную 0,5% от ширины картинки.
# Сам прикол в том что слева от линии будет левая часть первой картинки, а с другой
# стороны правая часть второй картинки. То есть по размеру она будет как картинка с
# большим разрешением. Но также должен быть переключатель, что будет делать линию
# горизонтальной, и соотвественно проводить манипуляции с картинками по горизонтали.
# Итоговая картинка сохраняется в png.
# В интерфейсе есть первая кнопка для выбора первой картиники, и вторая кнопка для
# выбора второй картинки. А снизу в окошке 600px по высоте будет отрисовываться
# итоговое изображение. А также будет кнопка объединить что будет сохранить
# итоговую картинку. Интерфейс нужен на pyqt6.
#
# --- Original script follows (unmodified) ---

import sys
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog, QSlider, QLabel, QCheckBox
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt, QRect
from PIL import Image
import numpy as np

class ImageComparisonApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.image1 = None
        self.image2 = None
        self.result_image = None
        self.is_horizontal = False

    def initUI(self):
        self.setWindowTitle('Image Comparison App')
        self.setGeometry(100, 100, 800, 800)

        layout = QVBoxLayout()

        # Buttons for image selection
        btn_layout = QHBoxLayout()
        self.btn_image1 = QPushButton('Select Image 1')
        self.btn_image2 = QPushButton('Select Image 2')
        self.btn_image1.clicked.connect(lambda: self.load_image(1))
        self.btn_image2.clicked.connect(lambda: self.load_image(2))
        btn_layout.addWidget(self.btn_image1)
        btn_layout.addWidget(self.btn_image2)
        layout.addLayout(btn_layout)

        # Slider for comparison
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(50)
        self.slider.valueChanged.connect(self.update_comparison)
        layout.addWidget(self.slider)

        # Checkbox for horizontal/vertical switch
        self.checkbox = QCheckBox('Horizontal Split')
        self.checkbox.stateChanged.connect(self.toggle_orientation)
        layout.addWidget(self.checkbox)

        # Label for displaying the image
        self.image_label = QLabel()
        self.image_label.setFixedSize(600, 600)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.image_label)

        # Button for saving the result
        self.btn_save = QPushButton('Save Result')
        self.btn_save.clicked.connect(self.save_result)
        layout.addWidget(self.btn_save)

        self.setLayout(layout)

    def load_image(self, image_number):
        file_name, _ = QFileDialog.getOpenFileName(self, f"Select Image {image_number}", "", "Image Files (*.png *.jpg *.bmp)")
        if file_name:
            image = Image.open(file_name)
            if image_number == 1:
                self.image1 = image
            else:
                self.image2 = image
            
            if self.image1 and self.image2:
                self.resize_images()
                self.update_comparison()

    def resize_images(self):
        max_width = max(self.image1.width, self.image2.width)
        max_height = max(self.image1.height, self.image2.height)

        self.image1 = self.image1.resize((max_width, max_height), Image.LANCZOS)
        self.image2 = self.image2.resize((max_width, max_height), Image.LANCZOS)

    def update_comparison(self):
        if self.image1 and self.image2:
            width, height = self.image1.size
            result = Image.new('RGB', (width, height))
            split_position = int(width * self.slider.value() / 100) if not self.is_horizontal else int(height * self.slider.value() / 100)

            if not self.is_horizontal:
                result.paste(self.image1.crop((0, 0, split_position, height)), (0, 0))
                result.paste(self.image2.crop((split_position, 0, width, height)), (split_position, 0))
            else:
                result.paste(self.image1.crop((0, 0, width, split_position)), (0, 0))
                result.paste(self.image2.crop((0, split_position, width, height)), (0, split_position))

            self.result_image = result
            self.display_result()

    def display_result(self):
        if self.result_image:
            qimage = self.result_image.toqimage()
            pixmap = QPixmap.fromImage(qimage)
            scaled_pixmap = pixmap.scaled(600, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            # Draw the comparison line
            painter = QPainter(scaled_pixmap)
            painter.setPen(QColor(0, 0, 0))
            if not self.is_horizontal:
                line_x = int(scaled_pixmap.width() * self.slider.value() / 100)
                line_width = max(1, int(scaled_pixmap.width() * 0.005))
                painter.drawRect(line_x - line_width // 2, 0, line_width, scaled_pixmap.height())
            else:
                line_y = int(scaled_pixmap.height() * self.slider.value() / 100)
                line_height = max(1, int(scaled_pixmap.height() * 0.005))
                painter.drawRect(0, line_y - line_height // 2, scaled_pixmap.width(), line_height)
            painter.end()

            self.image_label.setPixmap(scaled_pixmap)

    def toggle_orientation(self, state):
        self.is_horizontal = state == Qt.CheckState.Checked.value
        self.update_comparison()

    def save_result(self):
        if self.result_image:
            file_name, _ = QFileDialog.getSaveFileName(self, "Save Image", "", "PNG Files (*.png)")
            if file_name:
                self.result_image.save(file_name, 'PNG')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ImageComparisonApp()
    ex.show()
    sys.exit(app.exec())
