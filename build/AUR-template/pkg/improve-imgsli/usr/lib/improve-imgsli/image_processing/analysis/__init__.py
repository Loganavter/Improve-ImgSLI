"""
Модуль анализа изображений для Improve-ImgSLI.

Этот модуль содержит все алгоритмы анализа изображений, разделенные по функциональности:
- differ: функции поиска различий между изображениями
- edge_detector: детекция контуров
- channel_analyzer: анализ цветовых каналов
- metrics: расчет метрик качества (PSNR, SSIM)
"""

from .differ import create_highlight_diff, create_grayscale_diff, create_ssim_map
from .edge_detector import create_edge_map
from .channel_analyzer import extract_channel
from .metrics import calculate_psnr, calculate_ssim, calculate_metrics

__all__ = [
    'create_highlight_diff',
    'create_grayscale_diff',
    'create_ssim_map',
    'create_edge_map',
    'extract_channel',
    'calculate_psnr',
    'calculate_ssim',
    'calculate_metrics'
]

