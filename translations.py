# translations.py
from PyQt6.QtCore import QTranslator, QCoreApplication

translations = {
    'en': {
        'Select Image 1': 'Select Image 1',
        'Select Image 2': 'Select Image 2',
        'Horizontal Split': 'Horizontal Split',
        'Use Magnifier': 'Use Magnifier',
        'Freeze Magnifier': 'Freeze Magnifier',
        'Magnifier Size:': 'Magnifier Size:',
        'Capture Size:': 'Capture Size:',
        'Movement Speed:': 'Movement Speed:',
        'Save Result': 'Save Result',
        'Help': 'Help',
        'Drop Image 1 Here': 'Drop Image 1 Here',
        'Drop Image 2 Here': 'Drop Image 2 Here',
         'To move magnifying glasses separately from the detection area - use WASD keys. To change the distance between magnifying glasses - use Q and E keys. If the distance between them becomes too small, they will merge.': 'To move magnifying glasses separately from the detection area - use WASD keys. To change the distance between magnifying glasses - use Q and E keys. If the distance between them becomes too small, they will merge.',
        '⇄': '⇄'
    },
    'ru': {
        'Select Image 1': 'Выбрать изображение 1',
        'Select Image 2': 'Выбрать изображение 2',
        'Horizontal Split': 'Горизонтальное разделение',
        'Use Magnifier': 'Использовать лупу',
        'Freeze Magnifier': 'Зафиксировать лупу',
        'Magnifier Size:': 'Размер лупы:',
        'Capture Size:': 'Размер захвата:',
        'Movement Speed:': 'Скорость движения:',
        'Save Result': 'Сохранить результат',
        'Help': 'Помощь',
        'Drop Image 1 Here': 'Перетащите изображение 1 сюда',
        'Drop Image 2 Here': 'Перетащите изображение 2 сюда',
        'To move magnifying glasses separately from the detection area - use WASD keys. To change the distance between magnifying glasses - use Q and E keys. If the distance between them becomes too small, they will merge.': 'Для перемещения луп отдельно от области обнаружения используйте клавиши WASD. Для изменения расстояния между лупами используйте клавиши Q и E. Если расстояние между ними станет слишком маленьким, они сольются.',
         '⇄': '⇄'
    },
    'zh': {
        'Select Image 1': '选择图片1',
        'Select Image 2': '选择图片2',
        'Horizontal Split': '水平分割',
        'Use Magnifier': '使用放大镜',
        'Freeze Magnifier': '固定放大镜',
        'Magnifier Size:': '放大镜大小：',
        'Capture Size:': '捕获大小：',
        'Movement Speed:': '移动速度：',
        'Save Result': '保存结果',
        'Help': '帮助',
        'Drop Image 1 Here': '将图片1拖放到这里',
        'Drop Image 2 Here': '将图片2拖放到这里',
        'To move magnifying glasses separately from the detection area - use WASD keys. To change the distance between magnifying glasses - use Q and E keys. If the distance between them becomes too small, they will merge.': '要将放大镜与检测区域分开移动 - 使用WASD键。要更改放大镜之间的距离 - 使用Q和E键。如果它们之间的距离变得太小，它们将合并。',
        '⇄': '⇄'
    }
}

def tr(text, language='en'):
    return translations.get(language, translations['en']).get(text, text)
