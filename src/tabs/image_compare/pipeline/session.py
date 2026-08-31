"""ImageSession — per-session state holder (plan_image_pipeline.md Phase 5).

Thin-owner pattern (CODE_PATTERNS.md): SessionController stays a forwarder
(~150 LOC), all session-scoped state lives in ImageSession per session_id.

Holds SlotSource paths + PipelineCache + AbortSignal + legacy guards that
were previously globals on the single SessionController instance, causing
cross-session leaks when switching sessions. Pending guards are now aliased
to ImagePipeline._inflight single-flight (Phase 2A).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.image_processing.autocrop import CropService

from tabs.image_compare.pipeline.abort import AbortSignal
from tabs.image_compare.pipeline.cache import PipelineCache
from tabs.image_compare.pipeline.image_load_service import ImageLoadService
from tabs.image_compare.pipeline.pipeline import ImagePipeline


class _PendingImageLoadsProxy:
    """Set-like view onto pipeline._inflight for legacy pending image loads compat."""

    def __init__(self, pipeline: ImagePipeline):
        self._pipeline = pipeline

    def __contains__(self, key: object) -> bool:
        sig = self._pipeline._inflight.get(key)  # type: ignore[arg-type]
        if sig is None:
            return False
        try:
            return not sig.is_aborted()
        except Exception:
            return True

    def add(self, key: tuple[int, str]) -> None:
        if key not in self:
            try:
                self._pipeline._inflight[key] = AbortSignal()
            except Exception:
                pass

    def discard(self, key: tuple[int, str]) -> None:
        try:
            self._pipeline._inflight.pop(key, None)
        except Exception:
            pass

    def __iter__(self):
        # yield only live keys
        for k, sig in list(self._pipeline._inflight.items()):
            try:
                if not sig.is_aborted() and isinstance(k, tuple) and len(k) == 2 and isinstance(k[0], int):
                    yield k
            except Exception:
                continue

    def __len__(self) -> int:
        return sum(1 for _ in self.__iter__())

    def clear(self) -> None:
        for k in list(self):
            self.discard(k)


class _PendingFullLoadsProxy:
    """Dict-like view for legacy pending full loads compat.

    Counts live _inflight keys per slot (keys of shape (slot, path) or
    ("full", slot, path)). Mutations are reflected as synthetic _inflight
    entries with prefix ("__full_count__", slot).
    """

    def __init__(self, pipeline: ImagePipeline):
        self._pipeline = pipeline
        self._counts: dict[int, int] = {1: 0, 2: 0}

    def _live_count(self, slot: int) -> int:
        # prefer explicit counts if set, else derive from _inflight
        cnt = self._counts.get(slot, 0)
        if cnt:
            return cnt
        # fallback derive from _inflight keys with slot prefix
        try:
            return sum(
                1
                for k, sig in self._pipeline._inflight.items()
                if not sig.is_aborted()
                and isinstance(k, tuple)
                and len(k) >= 2
                and k[0] == slot
            )
        except Exception:
            return 0

    def __getitem__(self, key: int) -> int:
        return self._live_count(int(key))

    def __setitem__(self, key: int, value: int) -> None:
        self._counts[int(key)] = int(value)
        # keep _inflight in sync for alias consumers that inspect _inflight
        try:
            # remove stale synthetic keys for this slot
            for k in [k for k in list(self._pipeline._inflight.keys()) if isinstance(k, tuple) and k and k[0] == "__full_count__" and len(k) > 1 and k[1] == int(key)]:
                self._pipeline._inflight.pop(k, None)
            if int(value) > 0:
                self._pipeline._inflight[("__full_count__", int(key))] = AbortSignal()
        except Exception:
            pass

    def __contains__(self, key: object) -> bool:
        return int(key) in self._counts if isinstance(key, int) else False

    def get(self, key: int, default: int = 0) -> int:
        try:
            return self.__getitem__(int(key))
        except Exception:
            return default

    def __iter__(self):
        return iter(self._counts)

    def keys(self):
        return self._counts.keys()

    def items(self):
        return ((k, self.get(k)) for k in self._counts)

    def __len__(self) -> int:
        return len(self._counts)


@dataclass
class ImageSession:
    session_id: str
    crop_service: CropService = field(default_factory=CropService)
    cache: PipelineCache = field(default_factory=PipelineCache)
    pipeline: ImagePipeline = field(default_factory=ImagePipeline)
    abort: AbortSignal = field(default_factory=AbortSignal)
    _seq: int = 0
    pyramid_builds: set[int] = field(default_factory=set)
    loading_toast_uid_slot: dict[int, int] = field(default_factory=dict)

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
        # compat proxies (alias _inflight, not separate storage)
        object.__setattr__(self, "_image_loads_proxy", _PendingImageLoadsProxy(self.pipeline))
        object.__setattr__(self, "_full_loads_proxy", _PendingFullLoadsProxy(self.pipeline))

    @property
    def pending_image_loads(self):  # alias to _inflight live keys
        return self.__dict__.get("_image_loads_proxy", _PendingImageLoadsProxy(self.pipeline))

    @pending_image_loads.setter
    def pending_image_loads(self, value) -> None:
        # for tests that assign a set directly
        try:
            proxy = self.pending_image_loads
            proxy.clear()
            for k in value:
                proxy.add(k)
        except Exception:
            object.__setattr__(self, "_image_loads_proxy", value)

    # underscore aliases for legacy getattr(holder, "_pending_*")
    @property
    def _pending_image_loads(self):
        return self.pending_image_loads

    @_pending_image_loads.setter
    def _pending_image_loads(self, v) -> None:
        self.pending_image_loads = v

    @property
    def pending_full_loads(self):  # alias with dict-like counts
        return self.__dict__.get("_full_loads_proxy", _PendingFullLoadsProxy(self.pipeline))

    @pending_full_loads.setter
    def pending_full_loads(self, value) -> None:
        try:
            proxy = self.pending_full_loads
            if isinstance(value, dict):
                for k, v in value.items():
                    proxy[int(k)] = int(v)
            else:
                object.__setattr__(self, "_full_loads_proxy", value)
        except Exception:
            object.__setattr__(self, "_full_loads_proxy", value)

    @property
    def _pending_full_loads(self):
        return self.pending_full_loads

    @_pending_full_loads.setter
    def _pending_full_loads(self, v) -> None:
        self.pending_full_loads = v

    @property
    def unification_task_id(self) -> int:
        return int(self.__dict__.get("_seq", 0))

    @unification_task_id.setter
    def unification_task_id(self, v: int) -> None:
        try:
            self.__dict__["_seq"] = int(v)
            # keep abort generation in sync for alias consumers
            try:
                self.abort._generation = int(v)  # type: ignore[attr-defined]
            except Exception:
                pass
        except Exception:
            pass

    @property
    def _unification_task_id(self) -> int:
        return self.unification_task_id

    @_unification_task_id.setter
    def _unification_task_id(self, v: int) -> None:
        self.unification_task_id = v

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
