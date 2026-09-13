"""ImageLoadService — single-flight loader (phase 3 bucket D).

Single-flight via ``path+mtime → AbortSignal`` (ключ всегда boxless, см.
``pipeline/cache._pixel_key``: W1+W2 non-destructive crop — декод
full-frame, сервис только детекция). Заменяет:

* ``slot._inflight[(slot,path)]`` (slot.py:475)
* ``image_decode._inflight[(slot,path,"full")]`` (image_decode.py:272)
* ``unify (p1,p2)`` (unify.py:214)
* ``pyramid single-flight`` (session.py / pyramid.py)

Key ``(normpath, mtime_ns, size, False)``. CropService прогревается lazy
внутри GenericWorker (side-effect кэша сервиса — только детекция, в декод
и ключи не попадает), GUI не блокируется на sync ``crop_service.get(path)``
до ``pool.start``.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Callable

from sli_ui_toolkit.workers import GenericWorker

from tabs.image_compare.pipeline.abort import AbortSignal
from tabs.image_compare.debug import ic_preview_debug

logger = logging.getLogger("ImproveImgSLI")


def _key_for_path(path: str, crop_service=None, **_kw) -> tuple:
    """Ключ всегда boxless: (normpath,mtime,size,False). Сервис игнорируется.

    W1+W2: single-flight dedup обязан сходиться для всех читателей
    (``ensure_async`` кладёт с None, ``bg_dirty.is_loading`` спрашивает с
    живым сервисом) — поэтому has_crop всегда False, как раньше при
    выключенном кропе. Старые True-ключи миссуют и не коллизируют.
    """
    try:
        st = os.stat(path)
        mtime = int(getattr(st, "st_mtime_ns", 0) or 0)
        size = int(getattr(st, "st_size", 0) or 0)
    except OSError:
        mtime = 0
        size = 0
    return (os.path.normpath(str(path)), int(mtime), int(size), False)


def _unify_key(path1: str, path2: str, method: str) -> tuple:
    """Unify single-flight key — path+method (store also keyed by uid later)."""
    return (os.path.normpath(str(path1)), os.path.normpath(str(path2)), str(method))


def _pipeline_inflight(controller: Any) -> dict | None:
    """Return controller.pipeline._inflight (may alias the service dict)."""
    try:
        pl = getattr(controller, "pipeline", None)
        d = getattr(pl, "_inflight", None)
        return d if isinstance(d, dict) else None
    except Exception:
        return None


class ImageLoadService:
    """Single-flight loader with path+mtime+box dedup and progressive inside."""

    def __init__(
        self,
        cache: Any | None = None,
        get_crop_service: Callable[[], Any | None] | None = None,
        get_store: Callable[[], Any | None] | None = None,
        get_thread_pool: Callable[[], Any | None] | None = None,
    ) -> None:
        self._cache = cache
        self._get_crop_service = get_crop_service
        self._get_store = get_store
        self._get_thread_pool = get_thread_pool
        self._inflight: dict[tuple, AbortSignal] = {}

    def key_for(self, path: str, crop_service: Any | None = None) -> tuple:
        # W1+W2: single-flight ключи boxless — сессионный detection-сервис
        # здесь не резолвится (и никогда не дёргается crop_service.get:
        # off-GUI правило). Аргумент принят для совместимости и игнорируется.
        return _key_for_path(path, crop_service)

    def unify_key_for(self, path1: str, path2: str, method: str) -> tuple:
        return _unify_key(path1, path2, method)

    def is_loading(self, path: str, crop_service: Any | None = None) -> bool:
        key = self.key_for(path, crop_service)
        sig = self._inflight.get(key)
        if sig is None:
            return False
        try:
            return not sig.is_aborted()
        except Exception:
            return True

    def is_unify_loading(self, path1: str, path2: str, method: str) -> bool:
        key = self.unify_key_for(path1, path2, method)
        sig = self._inflight.get(key)
        if sig is None:
            return False
        try:
            return not sig.is_aborted()
        except Exception:
            return True

    def try_acquire(self, key: tuple) -> AbortSignal | None:
        existing = self._inflight.get(key)
        if existing is not None:
            try:
                if not existing.is_aborted():
                    return None
            except Exception:
                return None
            self._inflight.pop(key, None)
        sig = AbortSignal()
        self._inflight[key] = sig
        return sig

    def release(self, key: tuple, signal: AbortSignal | None) -> None:
        try:
            cur = self._inflight.get(key)
            if signal is None or cur is signal:
                self._inflight.pop(key, None)
        except Exception:
            pass

    def try_acquire_load(self, path: str, crop_service: Any | None = None) -> tuple[tuple, AbortSignal] | None:
        key = self.key_for(path, crop_service)
        sig = self.try_acquire(key)
        if sig is None:
            return None
        return (key, sig)

    def try_acquire_unify(self, path1: str, path2: str, method: str) -> tuple[tuple, AbortSignal] | None:
        key = self.unify_key_for(path1, path2, method)
        sig = self.try_acquire(key)
        if sig is None:
            return None
        return (key, sig)

    def ensure_async(
        self,
        path: str,
        slot: int,
        index_in_list: int,
        controller: Any,
    ) -> AbortSignal | None:
        # W1+W2: декод и ключи — всегда boxless (crop_service=None, no-bake).
        # Сессионный сервис остаётся только для детекции: воркер прогревает
        # им box-кэш (svc.get вне GUI), в load/put он не попадает.
        detect_service = None
        try:
            if self._get_crop_service is not None:
                detect_service = self._get_crop_service()
            else:
                detect_service = getattr(controller, "_get_crop_service", lambda: None)()
        except Exception:
            detect_service = None
        crop_service = None
        cache = self._cache
        try:
            sess = None
            if hasattr(controller, "_get_image_session"):
                try:
                    sess = controller._get_image_session()
                    if sess is not None and hasattr(sess, "cache"):
                        cache = sess.cache
                except Exception:
                    pass
            if cache is None:
                cache = getattr(getattr(controller, "pipeline", None), "cache", None)
        except Exception:
            pass
        key = self.key_for(path, crop_service)
        existing = self._inflight.get(key)
        if existing is not None:
            try:
                if not existing.is_aborted():
                    ic_preview_debug("ImageLoadService dedup path=%s key=%s", path, key)
                    return existing
            except Exception:
                return existing
            self._inflight.pop(key, None)
        try:
            hit = None
            if cache is not None:
                try:
                    hit = cache.get_pixel(path, crop_service)
                except Exception:
                    hit = None
                if hit is None:
                    try:
                        hit = cache.get_preview(path, crop_service)  # type: ignore
                    except Exception:
                        hit = None
            if hit is not None:
                try:
                    from core.state_management.actions import InvalidateGeometryCacheAction, SetImageSessionImageAction
                    store = getattr(controller, "store", None)
                    if store is None and self._get_store is not None:
                        try:
                            store = self._get_store()
                        except Exception:
                            store = None
                    if store is not None and hasattr(store, "transact"):
                        store.transact(
                            [SetImageSessionImageAction(slot=int(slot), image=hit), InvalidateGeometryCacheAction()],
                            scope="viewport",
                        )
                        ic_preview_debug("ImageLoadService cache-hit transact slot=%s path=%s", slot, path)
                except Exception as e:
                    ic_preview_debug("ImageLoadService cache-hit transact failed %s", e)
                return None
        except Exception:
            pass
        sig = AbortSignal()
        self._inflight[key] = sig
        ic_preview_debug("ImageLoadService start slot=%s path=%s key=%s sig=%s", slot, path, key, sig)

        def _worker_body(p: str, svc, sl, idx, sig_ref):
            # Прогрев detection-кэша CropService вне GUI-потока: svc.get
            # кэширует box внутри сервиса (для crop_box.py). Декод и put —
            # всегда boxless (no-bake, ключи без has_crop).
            try:
                if sig_ref.is_aborted():
                    return None, p, sl, idx, False
                if svc is not None and not isinstance(svc, bool):
                    try:
                        svc.get(p)  # type: ignore[union-attr]
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                from shared.image_processing.progressive_loader import should_use_progressive_load
                use_prog = should_use_progressive_load(p)
            except Exception:
                use_prog = False
            if use_prog:
                try:
                    from shared.image_processing.progressive_loader import load_preview_image
                    if sig_ref.is_aborted():
                        return None, p, sl, idx, False
                    preview = load_preview_image(p, crop_service=None)
                    if preview is not None and not getattr(preview, "isNull", lambda: True)():
                        try:
                            if cache is not None:
                                cache.put_preview(p, None, preview)
                        except Exception:
                            pass
                        return preview, p, sl, idx, True
                except Exception as e:
                    logger.debug("preview load failed %s: %s", p, e)
                try:
                    if sig_ref.is_aborted():
                        return None, p, sl, idx, False
                except Exception:
                    pass
            try:
                from shared.image_processing.pixel_cache_loader import load_pixel_store
                if sig_ref.is_aborted():
                    return None, p, sl, idx, False
                _emb_svc = None
                try:
                    _emb_svc = getattr(getattr(controller, "pipeline", None), "cache", None)
                except Exception:
                    _emb_svc = None
                store_obj = load_pixel_store(p, crop_service=None, embedded_cache=_emb_svc)
                try:
                    if sig_ref.is_aborted():
                        return None, p, sl, idx, False
                except Exception:
                    pass
                # put boxless (ключ без has_crop — см. cache._pixel_key)
                try:
                    if cache is not None and store_obj is not None:
                        cache.put_pixel(p, None, store_obj)
                except Exception:
                    pass
                return store_obj, p, sl, idx, False
            except Exception as e:
                logger.debug("pixel load failed %s: %s", p, e)
                return None, p, sl, idx, False

        pool = None
        try:
            if self._get_thread_pool is not None:
                pool = self._get_thread_pool()
            if pool is None:
                pool = getattr(controller, "thread_pool", None)
        except Exception:
            pool = getattr(controller, "thread_pool", None)

        def _pop_alias():
            # Pipeline alias (slot, path) set by the slot.py service path in
            # the shared _inflight dict. The service never knew this key shape,
            # so it leaked with a live signal forever: every later pyramid
            # start saw "decode in flight" and skipped the uid->slot toast
            # mapping, hanging the toast. Pop only if the entry is still ours
            # (a newer load may have reused the key).
            try:
                alias = (int(slot), str(path))
            except Exception:
                return
            dicts = [self._inflight]
            pl_d = _pipeline_inflight(controller)
            if pl_d is not None and pl_d is not self._inflight:
                dicts.append(pl_d)
            for d in dicts:
                try:
                    if d.get(alias) is sig:
                        d.pop(alias, None)
                except Exception:
                    pass

        def _on_result(result):
            try:
                cur = self._inflight.get(key)
                if cur is sig:
                    self._inflight.pop(key, None)
            except Exception:
                pass
            _pop_alias()
            try:
                controller._on_image_loaded(result)
            except Exception as e:
                ic_preview_debug("ImageLoadService _on_result handler failed %s", e)
                logger.exception("ImageLoadService result handler failed")

        def _on_finished():
            try:
                cur = self._inflight.get(key)
                if cur is sig:
                    self._inflight.pop(key, None)
            except Exception:
                pass
            _pop_alias()

        # svc несёт detection-сервис для прогрева box-кэша в воркере;
        # декод/put внутри _worker_body — всегда boxless (None).
        worker = GenericWorker(_worker_body, path, detect_service, int(slot), int(index_in_list), sig)
        worker.signals.result.connect(_on_result)
        try:
            worker.signals.finished.connect(_on_finished)
        except Exception:
            pass
        if pool is not None:
            try:
                pool.start(worker)
            except Exception as e:
                ic_preview_debug("ImageLoadService pool start failed %s", e)
                self._inflight.pop(key, None)
                return None
        else:
            ic_preview_debug("ImageLoadService no thread_pool, inline")
            self._inflight.pop(key, None)
        return sig

    @property
    def inflight(self) -> dict[tuple, AbortSignal]:
        return self._inflight
