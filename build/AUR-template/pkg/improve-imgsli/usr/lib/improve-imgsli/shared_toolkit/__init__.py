"""
Shared Toolkit - Общая библиотека для проектов Improve-ImgSLI и Tkonverter

Этот модуль содержит общие компоненты, используемые в обоих проектах:
- Утилиты для работы с файлами и путями
- UI компоненты (fluent widgets, менеджеры)
- Общие скрипты и функции
"""

from .utils import get_unique_filepath, resource_path
from .ui.widgets.atomic import (
    FluentCheckBox,
    CustomButton,
    CustomLineEdit,
    FluentComboBox,
    FluentRadioButton,
    FluentSwitch,
    FluentSlider,
    FluentSpinBox,
    BodyLabel,
    CaptionLabel,
    AdaptiveLabel,
    CompactLabel,
    GroupTitleLabel,
    CustomGroupWidget,
    CustomGroupBuilder,
    MinimalistScrollBar
)
from .ui.managers import ThemeManager
from .ui.services import IconService, get_icon_by_name, get_icon_service

__version__ = "1.1.0"
__author__ = "Loganavter"

__all__ = [
    'get_unique_filepath',
    'resource_path',
    'FluentCheckBox',
    'CustomButton',
    'CustomLineEdit',
    'FluentComboBox',
    'FluentRadioButton',
    'FluentSwitch',
    'FluentSlider',
    'FluentSpinBox',
    'BodyLabel',
    'CaptionLabel',
    'AdaptiveLabel',
    'CompactLabel',
    'GroupTitleLabel',
    'CustomGroupWidget',
    'CustomGroupBuilder',
    'MinimalistScrollBar',
    'ThemeManager',
    'IconService',
    'get_icon_by_name',
    'get_icon_service'
]
