"""
Утилиты для работы с файлами и путями.
"""

from .file_utils import get_unique_filepath
from .paths import resource_path

__all__ = ['get_unique_filepath', 'resource_path']
