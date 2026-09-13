"""CropService — явный кэш, без глобала и синглтона.

Владеет состоянием: один bbox на путь, вычисляется один раз через зонд
1024 с fallback thr15→thr30. Логика parity с бывшим get_crop_box /
_auto_crop_box_scaled: vips find_trim (thr) → PIL fallback, скейл через NEAREST.
"""
from __future__ import annotations

import os
import weakref
from pathlib import Path

import numpy as np
from PIL import Image

from .debug import autocrop_debug
from .model import CropBox, CropConfig, CropResult
from .pil import find_box_pil
from .vips import find_box_vips

import logging

logger = logging.getLogger("ImproveImgSLI")

# Реестр живых сервисов для глобальной инвалидации (не кэш bbox, а множество
# инстансов). Позволяет application_service инвалидировать все без синглтона.
_live_services: weakref.WeakSet = weakref.WeakSet()


def _register(service: "CropService") -> None:
    try:
        _live_services.add(service)
    except Exception:
        pass


def invalidate_all_services() -> None:
    for svc in list(_live_services):
        try:
            svc.invalidate_all()
        except Exception:
            pass


def schedule_crop_warmup(
    crop_service: "CropService | None", paths: list[str], thread_pool=None
) -> None:
    """Удобный хелпер для фонового прогрева CropService (long-term fix)."""
    if crop_service is None or not paths:
        return
    try:
        # delegate to service method (handles pooling)
        crop_service.warm_cache_async(paths, thread_pool=thread_pool)
    except Exception:
        pass


class CropService:
    """Явный сервис автокропа — инжектируется в PipelineCache / TiledPixelStore.

    Нет глобального dict, нет синглтона. Каждый инстанс владеет своим кэшем.
    """

    def __init__(self, config: CropConfig | None = None):
        self._config: CropConfig = config or CropConfig()
        # ключ — нормализованный путь, значение — CropResult | None (None = нет кропа)
        self._cache: dict[str, CropResult | None] = {}
        _register(self)

    # -- публичный API --

    def compute(self, path: str | Path) -> CropResult | None:
        """Вычислить (или вернуть кэшированный) CropResult для path.

        Пробует thr из config.thresholds() последовательно (15→30), возвращает
        первый не-None bbox. Кэширует и None (нет кропа) чтобы не переоткрывать.
        """
        key = os.path.normpath(os.fspath(path))
        if key in self._cache:
            return self._cache[key]
        result = self._compute_uncached(key)
        # Кэшируем даже None → «нет кропа» (как раньше _crop_box_cache[key]=None)
        self._cache[key] = result
        return result

    def get(self, path: str | Path) -> CropBox | None:
        """Удобный геттер — только bbox (или None)."""
        res = self.compute(path)
        if res is None:
            return None
        return res.box

    # Совместимость: старый код использовал get_crop_box -> tuple | None
    def get_crop_box(self, path: str | Path) -> tuple[int, int, int, int] | None:
        box = self.get(path)
        return box.to_tuple() if box is not None else None

    def invalidate(self, path: str | Path | None = None) -> None:
        """Сбросить кэш для path или весь."""
        if path is None:
            self.invalidate_all()
            return
        key = os.path.normpath(os.fspath(path))
        self._cache.pop(key, None)
        # Также пробуем без normpath на случай разных ключей (как раньше)
        self._cache.pop(os.fspath(path), None)

    def invalidate_all(self) -> None:
        self._cache.clear()

    # -- внутренности --

    def _compute_uncached(self, path_str: str) -> CropResult | None:
        # Пробуем каждый порог отдельно — семантика бывшей get_crop_box (thr15, иначе thr30)
        for thr in self._config.thresholds():
            box = self._box_for_threshold(path_str, thr)
            if box is not None:
                return CropResult(path=path_str, box=box, threshold=thr)
        autocrop_debug(
            "probe verdict=SKIP reason=no box under thr=%s path=%s",
            self._config.thresholds(), path_str,
        )
        return None

    def _box_for_threshold(self, path_str: str, thr: int) -> CropBox | None:
        """Одна попытка для заданного thr — открыть, сделать зонд, vips→pil, отскейлить."""
        try:
            # JXL может быть ndarray — но зонд-кэш в tiled_pixel_store открывал только PIL.
            # Для parity открываем PIL напрямую; если PIL не умеет (JXL без плагина),
            # пробуем imagecodecs как fallback (сохраняя parity с _auto_crop_box_from_ndarray).
            if path_str.lower().endswith(".jxl"):
                try:
                    import imagecodecs  # type: ignore

                    arr = imagecodecs.imread(path_str)
                    return self._box_from_ndarray(arr, thr)
                except Exception:
                    pass
            with Image.open(path_str) as im:
                im.load()
                rgba = im.convert("RGBA")
                return self._box_from_rgba(rgba, thr)
        except Exception as e:
            logger.debug("CropService box compute failed %s thr=%d: %s", path_str, thr, e)
            return None

    def _box_from_rgba(self, rgba: Image.Image, thr: int) -> CropBox | None:
        w, h = rgba.size
        longest = max(w, h)
        probe_max = int(self._config.probe_max)
        if longest <= probe_max:
            # Без даунскейла — пробуем vips напрямую на полном RGBA
            v = find_box_vips(np.asarray(rgba), threshold=thr)
            if v is not None:
                return v
            return find_box_pil(rgba, threshold=thr)

        scale = probe_max / float(longest)
        probe_w = max(1, int(round(w * scale)))
        probe_h = max(1, int(round(h * scale)))
        probe = rgba.resize((probe_w, probe_h), Image.Resampling.NEAREST)
        inv = 1.0 / scale

        # vips на зонде
        vb = find_box_vips(np.asarray(probe), threshold=thr)
        if vb is not None:
            pl, pt, pr, pb = vb.left, vb.top, vb.right, vb.bottom
        else:
            b = find_box_pil(probe, threshold=thr)
            if b is None:
                return None
            pl, pt, pr, pb = b.left, b.top, b.right, b.bottom

        left = max(0, int(round(pl * inv)))
        top = max(0, int(round(pt * inv)))
        right = min(w, max(left + 1, int(round(pr * inv))))
        bottom = min(h, max(top + 1, int(round(pb * inv))))
        if (left, top, right, bottom) == (0, 0, w, h):
            return None
        return CropBox(left, top, right, bottom)

    def _box_from_ndarray(self, arr: np.ndarray, thr: int) -> CropBox | None:
        """Аналог tiled_pixel_store._auto_crop_box_from_ndarray для JXL."""
        src_h, src_w = int(arr.shape[0]), int(arr.shape[1])
        longest = max(src_w, src_h)
        probe_max = int(self._config.probe_max)
        if longest <= probe_max:
            vb = find_box_vips(arr, threshold=thr)
            if vb is not None:
                return vb
            channels = arr[:, :, :3] if arr.shape[2] >= 3 else arr
            rgb = Image.fromarray(np.asarray(channels, dtype=np.uint8), mode="RGB")
            return find_box_pil(rgb.convert("RGBA"), threshold=thr)

        scale = probe_max / float(longest)
        inv = 1.0 / scale
        step = max(1, int(round(inv)))
        small = np.asarray(arr[::step, ::step, :3], dtype=np.uint8)

        vb = find_box_vips(small, threshold=thr)
        if vb is None:
            probe = Image.fromarray(small, mode="RGB").convert("RGBA")
            vb = find_box_pil(probe, threshold=thr)
            if vb is None:
                return None

        pl, pt, pr, pb = vb.left, vb.top, vb.right, vb.bottom
        left = max(0, int(round(pl * inv)))
        top = max(0, int(round(pt * inv)))
        right = min(src_w, max(left + 1, int(round(pr * inv))))
        bottom = min(src_h, max(top + 1, int(round(pb * inv))))
        if (left, top, right, bottom) == (0, 0, src_w, src_h):
            return None
        return CropBox(left, top, right, bottom)

    # -- интроспекция для тестов --

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def _has_cached(self, path: str | Path) -> bool:
        return os.path.normpath(os.fspath(path)) in self._cache

    # -- long-term fix: background warmup (отдельный crop cache прогрев) --
    def warm_cache_async(
        self, paths: list[str | Path], thread_pool=None
    ) -> None:
        """Прогреть кэш CropService в фоне без блока GUI.

        Запускает GenericWorker в thread_pool (или global QThreadPool) который
        вызывает self.compute для каждого path. GUI не ждёт результата.
        """
        if not paths:
            return
        # фильтрация уже кэшированных — без sync get вне воркера фильтрация по _has_cached ок (без IO)
        to_warm: list[str] = []
        for p in paths:
            try:
                key = os.path.normpath(os.fspath(p))
                if key not in self._cache:
                    to_warm.append(key)
            except Exception:
                continue
        if not to_warm:
            return

        def _warm(paths_: list[str], svc: "CropService"):
            for pp in paths_:
                try:
                    svc.compute(pp)
                except Exception:
                    pass

        try:
            from sli_ui_toolkit.workers import GenericWorker
        except Exception:
            # fallback sync warm (tests без Qt)
            for pp in to_warm:
                try:
                    self.compute(pp)
                except Exception:
                    pass
            return
        try:
            worker = GenericWorker(_warm, to_warm, self)
            pool = thread_pool
            if pool is None:
                try:
                    from PySide6.QtCore import QThreadPool

                    pool = QThreadPool.globalInstance()
                except Exception:
                    pool = None
            if pool is not None:
                pool.start(worker)
            else:
                # no pool — run inline (tests)
                for pp in to_warm:
                    try:
                        self.compute(pp)
                    except Exception:
                        pass
        except Exception:
            pass
