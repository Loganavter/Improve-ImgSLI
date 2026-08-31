"""ImagePipeline package — demand-driven decode/unify/pyramid pipeline.

Phase 1 skeleton: AbortSignal + PipelineCache + ImagePipeline are state-owning
collaborators (CODE_PATTERNS.md) that replace legacy dedup flags and QTimer
deferrals in session controller / loading.

Public surface:
  from tabs.image_compare.pipeline import ImagePipeline, PipelineCache, AbortSignal

See docs/dev/plan_image_pipeline.md Phase 1–2.
"""

from tabs.image_compare.pipeline.abort import AbortSignal
from tabs.image_compare.pipeline.cache import PipelineCache
from tabs.image_compare.pipeline.pipeline import ImagePipeline, PipelineView

__all__ = ["AbortSignal", "ImagePipeline", "PipelineCache", "PipelineView"]
