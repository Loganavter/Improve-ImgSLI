"""ImageLoadService — single-flight loader (phase 3 bucket D).

Single-flight via ``path+mtime+has_crop → AbortSignal`` (long-term fix:
без box_tuple, только has_crop). Заменяет:

* ``slot._inflight[(slot,path)]`` (slot.py:475)
* ``image_decode._inflight[(slot,path,"full")]`` (image_decode.py:272)
* ``unify (p1,p2)`` (unify.py:214)
* ``pyramid single-flight`` (session.py / pyramid.py)

Key теперь ``(normpath, mtime_ns, size, has_crop)`` — как
``_pixel_key`` без box; box вычисляется lazy внутри GenericWorker и
включается в put_pixel ключ отдельно, чтобы GUI не блокировался
sync crop_service.get(path) до pool.start.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Callable

from sli_ui_toolkit.workers import GenericWorker

from tabs.image_compare.pipeline.abort import AbortSignal
from tabs.image_compare.debug import ic_preview_debug

logger = logging.getLogger("ImproveImgSLI")


def _key_for_path(path: str, crop_service=None, box_tuple=None) -> tuple:
    """Long-term fix: key без box_tuple, только (normpath,mtime,size,has_crop).

    box вычисляется lazy внутри GenericWorker и включается в put_pixel ключ
    отдельно, чтобы GUI не делал sync crop_service.get(path) до pool.start.
    """
    has_crop = False
    if crop_service is not None and not isinstance(crop_service, bool):
        # do NOT call crop_service.get here — GUI block removed (was :47)
        has_crop = bool(crop_service)
    elif isinstance(crop_service, bool):
        has_crop = bool(crop_service)
    try:
        st = os.stat(path)
        mtime = int(getattr(st, "st_mtime_ns", 0) or 0)
        size = int(getattr(st, "st_size", 0) or 0)
    except OSError:
        mtime = 0
        size = 0
    # if box provided explicitly (worker-side lazy), include it for precise dedup
    if box_tuple is not None:
        return (os.path.normpath(str(path)), int(mtime), int(size), bool(has_crop), box_tuple)
    return (os.path.normpath(str(path)), int(mtime), int(size), bool(has_crop))


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
        if crop_service is None and self._get_crop_service is not None:
            try:
                crop_service = self._get_crop_service()
            except Exception:
                crop_service = None
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
        crop_service = None
        try:
            if self._get_crop_service is not None:
                crop_service = self._get_crop_service()
            else:
                crop_service = getattr(controller, "_get_crop_service", lambda: None)()
        except Exception:
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
            # Long-term fix: lazy box compute off GUI thread before pool load.
            # Warm CropService cache inside worker, not on GUI before start.
            box_tuple = None
            try:
                if sig_ref.is_aborted():
                    return None, p, sl, idx, False
                if svc is not None and not isinstance(svc, bool):
                    try:
                        b = svc.get(p)  # type: ignore[union-attr]
                        box_tuple = b.to_tuple() if b is not None else None
                    except Exception:
                        box_tuple = None
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
                    preview = load_preview_image(p, crop_service=svc)
                    if preview is not None and not getattr(preview, "isNull", lambda: True)():
                        # put preview with lazy box included for precise key
                        try:
                            if cache is not None and box_tuple is not None:
                                cache.put_preview(p, svc, preview, box_tuple=box_tuple)  # type: ignore
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
                store_obj = load_pixel_store(p, crop_service=svc, embedded_cache=_emb_svc)
                try:
                    if sig_ref.is_aborted():
                        return None, p, sl, idx, False
                except Exception:
                    pass
                # lazy put with box_tuple for precise key (GUI will fallback scan if needed)
                try:
                    if cache is not None and store_obj is not None and box_tuple is not None:
                        cache.put_pixel(p, svc, store_obj, box_tuple=box_tuple)  # type: ignore
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

        worker = GenericWorker(_worker_body, path, crop_service, int(slot), int(index_in_list), sig)
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
