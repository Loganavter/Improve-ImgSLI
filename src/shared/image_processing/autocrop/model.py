"""Autocrop models — явные типы для bbox и конфигурации.

CropBox — bbox в координатах исходника (left, top, right, bottom).
CropResult — результат вычисления для пути (box + thr + probe).
CropConfig — настраиваемые пороги и максимальный размер зонда.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import NamedTuple


class SkipReason:
    """Стабильный словарь причин verdict=SKIP (box is None).

    ``box is None`` раньше означало сразу три разных исхода, и кэш
    ``CropService`` запоминал их одним ``None`` без различия — замена файла
    после «нет полей» залипала на stale-None. Различай:

    - ``BORDERLESS`` — файл читается, чёрных полей нет (честный None);
    - ``UNDECODABLE`` — файл не открылся/не декодировался (повторный probe
      может помочь, кэшировать надолго нельзя);
    - ``REPLACED_FILE`` — stat пути изменился после вычисления (старый
      результат недействителен, нужен пересчёт);
    - ``OVERSIZED`` — зонд пропущен по backend-bound (wave-1 decode-bounds),
      не декодировали вовсе;
    - ``DISABLED`` — crop_service отсутствует (настройка выключена).
    """

    BORDERLESS = "borderless"
    UNDECODABLE = "undecodable"
    REPLACED_FILE = "replaced-file"
    OVERSIZED = "oversized"
    DISABLED = "disabled"


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

    box == None — чёрных полей нет (или файл не читается): конкретную
    причину см. в ``reason`` (``SkipReason.*``). ``reason is None`` у старых
    записей означает «неизвестно» (legacy, до введения словаря).
    threshold — порог, на котором нашли bbox (None если box is None).
    probe_size — размер зонда, если применялся даунскейл (см.
    ``with_probe`` — вычисляется из исходного размера и probe_max той же
    математикой, что зонд в CropService).
    """

    path: str
    box: CropBox | None
    threshold: int | None = None
    probe_size: tuple[int, int] | None = None
    reason: str | None = None

    def to_tuple(self) -> tuple[int, int, int, int] | None:
        return self.box.to_tuple() if self.box is not None else None

    def with_probe(
        self, source_size: tuple[int, int], probe_max: int = 1024
    ) -> "CropResult":
        """Вернуть копию с назначенным ``probe_size``.

        Единственное место, где размер зонда вычисляется (та же формула,
        что даунскейл зонда в CropService: longest side → probe_max через
        NEAREST-скейл): полный кадр (longest <= probe_max) даёт
        ``probe_size == source_size`` (зонда-даунскейла не было, probe шел
        на полном кадре), иначе — уменьшенные dims. Явное назначение вместо
        вечного None: тесты и диагностика видят, на чём реально шёл probe.
        """
        return replace(
            self, probe_size=probe_dims(tuple(source_size), int(probe_max))
        )


def probe_dims(source_size: tuple[int, int], probe_max: int) -> tuple[int, int]:
    """Размер зонда для исходника — та же математика, что в CropService.

    ``source_size`` — (w, h) полного кадра; ``probe_max`` — максимум длинной
    стороны (CropConfig.probe_max). Чистая функция: детерминирована,
    geometry-only (не зависит от данных пикселей).
    """
    w, h = int(source_size[0]), int(source_size[1])
    longest = max(w, h)
    if longest <= int(probe_max):
        return (w, h)
    scale = float(probe_max) / float(longest)
    return (max(1, int(round(w * scale))), max(1, int(round(h * scale))))


def file_stat(path: str | os.PathLike) -> tuple[int | None, int | None]:
    """(mtime_ns, size) пути; (None, None) если stat недоступен.

    Контент-входы для ключей кэша (закон CONTENT IDENTITY): один путь —
    не identity, файл могли заменить. stat дешёвый (без декода).
    """
    try:
        st = os.stat(os.fspath(path))
        return (int(st.st_mtime_ns), int(st.st_size))
    except OSError:
        return (None, None)


def content_key(
    path: str | os.PathLike,
    *,
    mtime_ns: int | None = None,
    file_size: int | None = None,
) -> tuple[str, int | None, int | None]:
    """Ключ кэша для пути с контент-входами: (normpath, mtime_ns, size).

    Явные mtime/size имеют приоритет (вызыватель уже сделал stat); иначе
    stat делается здесь. Замена файла меняет ключ автоматически — stale
    None/content не залипает.
    """
    key = os.path.normpath(os.fspath(path))
    if mtime_ns is None or file_size is None:
        current_mtime, current_size = file_stat(key)
        if mtime_ns is None:
            mtime_ns = current_mtime
        if file_size is None:
            file_size = current_size
    return (key, mtime_ns, file_size)
