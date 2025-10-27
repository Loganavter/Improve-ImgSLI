"""
UI Services - Общие сервисы для пользовательского интерфейса.

Этот модуль содержит сервисы, которые используются в UI компонентах:
- IconService: Универсальный сервис для работы с иконками
"""

from .icon_service import IconService, get_icon_by_name, get_icon_service

__all__ = [
    'IconService',
    'get_icon_by_name',
    'get_icon_service'
]
