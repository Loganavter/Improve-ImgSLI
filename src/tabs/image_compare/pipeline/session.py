"""ImageSession — per-session state holder (plan_image_pipeline.md Phase 5).

Thin-owner pattern (CODE_PATTERNS.md): SessionController stays a forwarder
(~150 LOC), all session-scoped state lives in ImageSession per session_id.

Holds SlotSource paths + PipelineCache + AbortSignal per session.
"""

from __future__ import annotations

import weakref
from dataclasses import dataclass, field

from shared.image_processing.autocrop import CropService

from tabs.image_compare.pipeline.abort import AbortSignal
from tabs.image_compare.pipeline.cache import PipelineCache
from tabs.image_compare.pipeline.pipeline import ImagePipeline

# Реестр живых сессий для глобальной синхронизации crop-дефолта с настройкой
# auto_crop_black_borders (прецедент: CropService._live_services). Без этого
# PipelineCache/ImagePipeline fallback `else self.crop_service` воскрешает кроп
# при выключенной настройке: голый None от _get_crop_service() неотличим от
# "дефолт сессии", и preview-tier грузился обрезанным вопреки вердикту SKIP.
#
# NB: ImageSession — @dataclass с eq по умолчанию, т.е. нехешируемый, поэтому
# не WeakSet, а id-ключи со слабыми ссылками (семантику класса не трогаем).
_live_sessions: dict[int, weakref.ReferenceType] = {}


def _register_session(sess: "ImageSession") -> None:
    try:
        key = id(sess)
        _live_sessions[key] = weakref.ref(
            sess, lambda _r, _k=key: _live_sessions.pop(_k, None)
        )
    except Exception:
        pass


def set_sessions_crop_enabled(enabled: bool) -> None:
    """Синхронизировать crop-дефолт всех живых сессий с настройкой.

    OFF → sess.crop_service/cache.crop_service = None (голый None внизу по
    течению значит "выключено", а не "дефолт сессии"). ON → гарантировать живой
    сервис (старый мог быть занулён). Боксы детерминированы, закэшированные
    записи под has_crop=True/False остаются валидны после тоггла.
    """
    for ref in list(_live_sessions.values()):
        try:
            sess = ref()
        except Exception:
            continue
        if sess is None:
            continue
        try:
            sess.sync_crop_service(bool(enabled))
        except Exception:
            pass


@dataclass
class ImageSession:
    session_id: str
    crop_service: CropService = field(default_factory=CropService)
    cache: PipelineCache = field(default_factory=PipelineCache)
    pipeline: ImagePipeline = field(default_factory=ImagePipeline)
    abort: AbortSignal = field(default_factory=AbortSignal)
    _seq: int = 0
    pyramid_builds: set[int] = field(default_factory=set)

    def __post_init__(self):
        # wire pipeline to this session's cache + crop_service
        try:
            self.pipeline.cache = self.cache
            self.cache.crop_service = self.crop_service
        except Exception:
            pass
        _register_session(self)
        # single-flight loader (bucket D) — shares _inflight dict with pipeline
        try:
            from tabs.image_compare.pipeline.image_load_service import ImageLoadService as _ILS

            svc = _ILS(
                cache=self.cache,
                get_crop_service=lambda _self=self: getattr(_self, "crop_service", None),
            )
            # share single-flight dict: pipeline._inflight is alias to svc._inflight
            try:
                svc._inflight = self.pipeline._inflight  # type: ignore[attr-defined]
            except Exception:
                self.pipeline._inflight = svc._inflight  # type: ignore[attr-defined]
            object.__setattr__(self, "load_service", svc)
            # expose on pipeline for direct access (controller.pipeline.load_service)
            try:
                self.pipeline.load_service = svc  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass

    def sync_crop_service(self, enabled: bool) -> None:
        """Привести crop-дефолт сессии в соответствие с настройкой.

        Вызывать при создании сессии и при тоггле auto_crop_black_borders
        (см. set_sessions_crop_enabled). OFF зануляет и sess.crop_service
        (его читает ImageLoadService.get_crop_service), и cache.crop_service
        (fallback в PipelineCache/ImagePipeline) — иначе голый None внизу
        resurrection'ится в живой дефолт и кроп применяется вопреки настройке.
        """
        try:
            if enabled:
                if self.crop_service is None:
                    self.crop_service = CropService()
                self.cache.crop_service = self.crop_service
            else:
                self.crop_service = None
                self.cache.crop_service = None
        except Exception:
            pass

    def new_abort(self) -> AbortSignal:
        try:
            self.abort.abort()
        except Exception:
            pass
        self._seq += 1
        sig = AbortSignal()
        try:
            sig._generation = int(self._seq)  # type: ignore[attr-defined]
        except Exception:
            pass
        self.abort = sig
        return self.abort
