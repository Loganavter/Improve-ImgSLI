"""Autocrop models — явные типы для bbox и конфигурации.

CropBox — bbox в координатах исходника (left, top, right, bottom).
CropResult — результат вычисления для пути (box + thr + probe).
CropConfig — настраиваемые пороги и максимальный размер зонда.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


class CropBox(NamedTuple):
    """Прямоугольник обрезки в пикселях исходника.

    Инвариант: left < right, top < bottom, всё в пределах исходника.
    Равен (0,0,w,h) — означает «не обрезать».
    """

    left: int
    top: int
    right: int
    bottom: int

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (int(self.left), int(self.top), int(self.right), int(self.bottom))

    @property
    def width(self) -> int:
        return int(self.right - self.left)

    @property
    def height(self) -> int:
        return int(self.bottom - self.top)

    def is_full(self, size: tuple[int, int]) -> bool:
        w, h = size
        return self.left == 0 and self.top == 0 and self.right == w and self.bottom == h


@dataclass(frozen=True)
class CropConfig:
    """Конфигурация автокропа.

    thr/thr_fallback — пороги яркости для поиска чёрных полей (thr15→thr30),
    probe_max — максимальный размер длинной стороны зонда (1024 по умолчанию).
    """

    thr: int = 15
    thr_fallback: int = 30
    probe_max: int = 1024

    def thresholds(self) -> tuple[int, ...]:
        if self.thr == self.thr_fallback:
            return (int(self.thr),)
        return (int(self.thr), int(self.thr_fallback))


@dataclass(frozen=True)
class CropResult:
    """Результат автокропа для пути.

    box == None — чёрных полей нет (или файл не читается).
    threshold — порог, на котором нашли bbox (None если box is None).
    probe_size — размер зонда, если применялся даунскейл.
    """

    path: str
    box: CropBox | None
    threshold: int | None = None
    probe_size: tuple[int, int] | None = None

    def to_tuple(self) -> tuple[int, int, int, int] | None:
        return self.box.to_tuple() if self.box is not None else None
