from __future__ import annotations

import inspect
import json
import logging
import os
import sys
import threading
import uuid
from collections import deque
from dataclasses import fields, is_dataclass
from typing import Any, Iterable

from .records import TraceRecord, now

logger = logging.getLogger("ImproveImgSLI")

_DEFAULT_RING_SIZE = 4096
_SKIP_MODULE_PREFIXES = (
    "core.tracing.",
    "logging",
    "threading",
)

class Tracer:
    _instance: "Tracer | None" = None

    def __init__(self, ring_size: int = _DEFAULT_RING_SIZE):
        self._lock = threading.Lock()
        self._buffer: deque[TraceRecord] = deque(maxlen=ring_size)
        self._seq = 0
        self._enabled = True
        self._depth = threading.local()
        self._trace_id = threading.local()
        self._subscribers: list = []
        self._allow_kinds: tuple[str, ...] | None = None
        self._skip_kinds: tuple[str, ...] = ()
        self._span_counter = 0
        self._load_filter_from_env()

    def next_span_id(self) -> int:
        with self._lock:
            self._span_counter += 1
            return self._span_counter

    def _load_filter_from_env(self) -> None:
        allow = os.environ.get("IMGSLI_TRACE_KINDS", "").strip()
        skip = os.environ.get("IMGSLI_TRACE_SKIP", "").strip()
        if allow:
            self._allow_kinds = tuple(p.strip() for p in allow.split(",") if p.strip())
        if skip:
            self._skip_kinds = tuple(p.strip() for p in skip.split(",") if p.strip())
        else:

            self._skip_kinds = ("input.mmove",)

    def _kind_passes_filter(self, kind: str) -> bool:
        for pat in self._skip_kinds:
            if _match_kind(kind, pat):
                return False
        if self._allow_kinds is None:
            return True
        for pat in self._allow_kinds:
            if _match_kind(kind, pat):
                return True
        return False

    @classmethod
    def instance(cls) -> "Tracer":
        if cls._instance is None:
            cls._instance = Tracer()
        return cls._instance

    @classmethod
    def enabled(cls) -> bool:
        return cls._instance is not None and cls._instance._enabled

    def disable(self) -> None:
        self._enabled = False

    def enable(self) -> None:
        self._enabled = True

    def get_records(self) -> list[TraceRecord]:
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._seq = 0

    def subscribe(self, callback) -> None:
        self._subscribers.append(callback)

    def _current_depth(self) -> int:
        return getattr(self._depth, "value", 0)

    def _push_depth(self) -> None:
        self._depth.value = self._current_depth() + 1

    def _pop_depth(self) -> None:
        self._depth.value = max(0, self._current_depth() - 1)

    def current_trace_id(self) -> str | None:
        return getattr(self._trace_id, "value", None)

    def begin_trace(self, label: str | None = None) -> str:
        tid = (label + "-" if label else "") + uuid.uuid4().hex[:8]
        self._trace_id.value = tid
        return tid

    def end_trace(self) -> None:
        self._trace_id.value = None

    def record(
        self,
        kind: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        caller_skip: int = 1,
    ) -> TraceRecord | None:
        if not self._enabled:
            return None
        if not self._kind_passes_filter(kind):
            return None
        caller = _format_caller(caller_skip + 1)
        with self._lock:
            self._seq += 1
            rec = TraceRecord(
                seq=self._seq,
                ts=now(),
                kind=kind,
                trace_id=self.current_trace_id(),
                depth=self._current_depth(),
                summary=summary,
                caller=caller,
                payload=payload or {},
            )
            self._buffer.append(rec)
        for cb in list(self._subscribers):
            try:
                cb(rec)
            except Exception:
                logger.debug("tracer subscriber failed", exc_info=True)
        return rec

    def dump_json(self, path: str | None = None) -> str:
        records = [r.to_dict() for r in self.get_records()]
        text = json.dumps(records, indent=2, default=_json_default)
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(text)
            except OSError as exc:
                logger.warning("tracer dump failed: %s", exc)
        return text

def _match_kind(kind: str, pattern: str) -> bool:
    if pattern == kind:
        return True
    if pattern.endswith(".*") and kind.startswith(pattern[:-1]):
        return True
    if pattern.endswith("*") and kind.startswith(pattern[:-1]):
        return True
    return False

def _format_caller(skip: int) -> str:
    frame = sys._getframe(0)
    try:
        for _ in range(skip):
            if frame.f_back is None:
                break
            frame = frame.f_back
        while frame is not None:
            module = frame.f_globals.get("__name__", "")
            if not any(module.startswith(p) for p in _SKIP_MODULE_PREFIXES):
                return f"{module}:{frame.f_code.co_name}:{frame.f_lineno}"
            frame = frame.f_back
    finally:
        del frame
    return "<unknown>"

def _json_default(value: Any) -> Any:
    try:
        return repr(value)
    except Exception:
        return "<unrepr>"

def diff_dataclass(old: Any, new: Any, max_fields: int = 16) -> dict[str, Any]:
    if old is None or new is None or old is new:
        return {}
    if type(old) is not type(new):
        return {"<replaced>": True}

    if is_dataclass(new):
        field_names = [f.name for f in fields(new)]
    else:
        slots = getattr(type(new), "__slots__", None)
        if slots is None:
            try:
                field_names = list(vars(new).keys())
            except TypeError:
                return {}
        else:
            field_names = list(slots)

    changes: dict[str, Any] = {}
    for name in field_names:
        try:
            old_v = getattr(old, name)
            new_v = getattr(new, name)
        except AttributeError:
            continue
        if old_v is new_v:
            continue
        try:
            if old_v == new_v:
                continue
        except Exception:
            pass
        if is_dataclass(new_v) or hasattr(type(new_v), "__slots__"):
            try:
                nested = diff_dataclass(old_v, new_v, max_fields=max_fields)
                if nested:
                    changes[name] = nested
                continue
            except Exception:
                pass
        changes[name] = {"old": _short_repr(old_v), "new": _short_repr(new_v)}
        if len(changes) >= max_fields:
            changes["<truncated>"] = True
            break
    return changes

def _short_repr(value: Any, limit: int = 120) -> str:
    try:
        text = repr(value)
    except Exception:
        text = "<unrepr>"
    if len(text) > limit:
        text = text[:limit] + "…"
    return text

def is_trace_env_enabled() -> bool:
    return os.environ.get("IMGSLI_TRACE", "0") not in ("0", "", "false", "False")
