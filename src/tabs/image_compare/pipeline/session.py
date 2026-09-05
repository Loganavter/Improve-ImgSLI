"""ImageSession — per-session state holder (plan_image_pipeline.md Phase 5).

Thin-owner pattern (CODE_PATTERNS.md): SessionController stays a forwarder
(~150 LOC), all session-scoped state lives in ImageSession per session_id.

Holds SlotSource paths + PipelineCache + AbortSignal per session.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.image_processing.autocrop import CropService

from tabs.image_compare.pipeline.abort import AbortSignal
from tabs.image_compare.pipeline.cache import PipelineCache
from tabs.image_compare.pipeline.pipeline import ImagePipeline


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
