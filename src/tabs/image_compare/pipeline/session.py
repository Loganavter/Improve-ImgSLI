"""ImageSession — per-session state holder (plan_image_pipeline.md Phase 5).

Thin-owner pattern (CODE_PATTERNS.md): SessionController stays a forwarder
(~150 LOC), all session-scoped state lives in ImageSession per session_id.

Holds SlotSource paths + PipelineCache + AbortSignal + pending guards that
were previously globals on the single SessionController instance, causing
cross-session leaks when switching sessions.
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
    # guards that were controller._pending_* / _unification_task_id / _pyramid_builds
    pending_full_loads: dict[int, int] = field(default_factory=lambda: {1: 0, 2: 0})
    pending_image_loads: set[tuple[int, str]] = field(default_factory=set)
    unification_task_id: int = 0
    pyramid_builds: set[int] = field(default_factory=set)
    loading_toast_uid_slot: dict[int, int] = field(default_factory=dict)

    def __post_init__(self):
        # wire pipeline to this session's cache + crop_service
        try:
            self.pipeline.cache = self.cache
            self.cache.crop_service = self.crop_service
        except Exception:
            pass

    def new_abort(self) -> AbortSignal:
        try:
            self.abort.abort()
        except Exception:
            pass
        self.abort = AbortSignal()
        return self.abort
