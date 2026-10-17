"""Long-work inventory + cancel for the control channel (MCP v2 P3).

The control channel's answer to "an agent must be able to *watch and stop* the
passes that take minutes". This module is a **read view over state the app
already keeps** plus one real cancellation; it never tracks work of its own and
never invents a percentage (see ``docs/dev/MCP.md`` § Jobs).

Four kinds, in the priority the plan set:

* gallery_pool — the dedicated gallery thumbnail/proxy thread pool.
  Depth from ``GalleryController.sched_stats()`` (``use_cases/scheduler.py``);
  per-item progress from each ``GalleryItem.thumbnail_status``.
* metrics_pass — the per-folder Stage-2 metrics pass. Chunk progress is the
  controller's own ``_proxy_total`` / ``_proxy_done`` pair, the same numbers
  the app feeds ``widget.set_background_scanning(done, total)``.
* ai_analysis — the AI/VLM scorecard pass. There is no batch object: the
  aggregate is derived per item from ``item.analysis_status``.
* export — a still-image save. One job per in-flight save task, read from
  the shared save-flow coordinator's own ``_save_cancellation`` registry
  (``src/tabs/_shared/save_flow.py``); message/progress come from that task's
  toast when the toast manager is already materialized.

**Cancel is honest.** ``jobs_cancel`` sets the export task's real
``threading.Event`` — the same handle the toast's Cancel button sets, honored by
``ExportService`` and by ``write_pil_image_cancelable`` (atomic tmp+replace, the
tmp is removed on abort, so no partial artifact reaches the output path).
Nothing else in the app has a safe cancel today: the gallery pool is a Qt thread
pool (``clear()`` would silently drop queued thumbnails), the metrics pass and
the AI pass carry no cooperative token. Those kinds answer a *named* refusal
instead of a fake cancel.

**No concrete tab is imported** (host isolation contract): a gallery owner is
recognised by duck typing (``sched_stats`` + ``state.items``), a save flow by
its ``_save_cancellation`` mapping. Status values are compared as strings, the
same way the gallery's activity helper reads its enums without a Qt import.

**Live only.** Jobs are in-memory state of a running app; the headless fallback
has none, so the MCP side answers an honest error there (never an empty list
that would read as "nothing is running").
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .discovery import MethodError

#: The frozen row shape (one entry of ``jobs_list.jobs``).
JOB_KEYS: tuple[str, ...] = ("id", "kind", "status", "progress", "elapsed_s", "message")

#: Kind ids, in the plan's priority order.
KIND_GALLERY_POOL = "gallery_pool"
KIND_METRICS_PASS = "metrics_pass"
KIND_AI_ANALYSIS = "ai_analysis"
KIND_EXPORT = "export"

KINDS: tuple[str, ...] = (
    KIND_GALLERY_POOL,
    KIND_METRICS_PASS,
    KIND_AI_ANALYSIS,
    KIND_EXPORT,
)

#: Kinds with a real, safe cancel today. Export only.
CANCELLABLE_KINDS: tuple[str, ...] = (KIND_EXPORT,)

#: Enum values read as plain strings (no gallery import — see module docstring).
_THUMB_DONE = ("loaded", "error")
_AI_ACTIVE = ("pending",)
_AI_SETTLED = ("done", "error")

#: ``id -> monotonic stamp`` of the first ``jobs_list`` that saw the job active.
#: Dropped the moment the job leaves the list, so a later run of the same id
#: starts its clock over. App-process scoped (not per connection).
_OBSERVED_SINCE: dict[str, float] = {}


def _enum_value(value: Any) -> str:
    """``AnalysisStatus.PENDING`` / ``"pending"`` → ``"pending"``."""
    return str(getattr(value, "value", value) or "").lower()


def _progress(done: int, total: int) -> dict[str, int] | None:
    """Frozen progress shape, or ``None`` when the total is unknown."""
    if total <= 0:
        return None
    return {"done": int(done), "total": int(total)}


def _elapsed(job_id: str, active: bool) -> float | None:
    """Seconds this job has been *continuously observed* active, else ``None``.

    The app does not stamp a start time for these passes, so this is measured
    from the first ``jobs_list`` that saw the job running. It is a lower bound,
    never a guess — documented as such in ``docs/dev/MCP.md``.
    """
    if not active:
        _OBSERVED_SINCE.pop(job_id, None)
        return None
    start = _OBSERVED_SINCE.setdefault(job_id, time.monotonic())
    return round(time.monotonic() - start, 1)


def _row(job_id: str, kind: str, status: str, progress: Any, message: str) -> dict[str, Any]:
    return {
        "id": job_id,
        "kind": kind,
        "status": status,
        "progress": progress,
        "elapsed_s": _elapsed(job_id, status != "idle"),
        "message": message,
    }


def _unique_key(seen: set[str], session_type: str, index: int) -> str:
    """A stable-per-call key: the tab type, disambiguated when duplicated."""
    key = str(session_type)
    if index:  # a second live copy of the same tab type (session isolation)
        key = f"{key}#{index}"
    while key in seen:
        key = f"{key}#"
    seen.add(key)
    return key


# ---------------------------------------------------------------------------
# gallery owners (thumbnail/proxy pool, metrics pass, AI analysis)
# ---------------------------------------------------------------------------


def _gallery_owners(tabs: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Live tab objects that own a gallery controller (duck-typed)."""
    owners: list[tuple[str, Any]] = []
    seen: set[str] = set()
    counts: dict[str, int] = {}
    for session_type, tab in tabs:
        controller = getattr(tab, "_controller", None)
        if controller is None or not callable(getattr(controller, "sched_stats", None)):
            continue
        index = counts.get(str(session_type), 0)
        counts[str(session_type)] = index + 1
        owners.append((_unique_key(seen, session_type, index), controller))
    return owners


def _items_of(owner: Any) -> list[Any]:
    try:
        return list(getattr(getattr(owner, "state", None), "items", None) or [])
    except Exception:
        return []


def _gallery_jobs(key: str, owner: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    items = _items_of(owner)
    try:
        stats = owner.sched_stats() or {}
    except Exception:
        stats = {}
    pending = int(stats.get("pending") or 0)
    active = int(stats.get("active") or 0)
    queued = int(stats.get("queued") or 0)

    total = len(items)
    loaded = sum(1 for it in items if _enum_value(getattr(it, "thumbnail_status", None)) in _THUMB_DONE)
    outstanding = pending + active + queued
    if outstanding:
        paused = bool(getattr(owner, "_bg_paused", False)) and active == 0
        status = "paused" if paused else "running"
        rows.append(
            _row(
                f"pool:{key}",
                KIND_GALLERY_POOL,
                status,
                _progress(loaded, total),
                f"thumbnails {loaded}/{total} loaded "
                f"({active} active, {pending} pending, {queued} queued)",
            )
        )

    proxy_total = int(getattr(owner, "_proxy_total", 0) or 0)
    proxy_done = int(getattr(owner, "_proxy_done", 0) or 0)
    if proxy_total > 0 and proxy_done < proxy_total:
        rows.append(
            _row(
                f"metrics:{key}",
                KIND_METRICS_PASS,
                "running",
                _progress(proxy_done, proxy_total),
                f"metrics pass {proxy_done}/{proxy_total} chunks applied",
            )
        )

    ai_active = ai_settled = 0
    for it in items:
        value = _enum_value(getattr(it, "analysis_status", None))
        if value in _AI_ACTIVE:
            ai_active += 1
        elif value in _AI_SETTLED:
            ai_settled += 1
    if ai_active:
        rows.append(
            _row(
                f"ai:{key}",
                KIND_AI_ANALYSIS,
                "running",
                _progress(ai_settled, ai_active + ai_settled),
                f"AI analysis {ai_settled}/{ai_active + ai_settled} items settled",
            )
        )
    return rows


# ---------------------------------------------------------------------------
# export save flows
# ---------------------------------------------------------------------------


def _resolved_service(service: Any) -> Any:
    """A ``LazyTabService``'s *already built* service — never triggers a build.

    ``jobs_list`` is read-only: resolving a lazy tab service would materialize
    a tab as a side effect of listing, so an unresolved service is skipped.
    """
    if service is None:
        return None
    if hasattr(service, "_resolved") and hasattr(service, "_tried"):
        return getattr(service, "_resolved") if getattr(service, "_tried", False) else None
    return service


def _save_flows(window: Any, tabs: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Live save-flow coordinators, keyed by the tab type that owns them."""
    flows: list[tuple[str, Any]] = []
    seen: set[str] = set()
    features = getattr(getattr(window, "presenter", None), "features", None)
    presenter = _resolved_service(getattr(features, "export", None))
    flow = getattr(getattr(presenter, "save_flow", None), "_flow", None)
    if flow is not None:
        # The still-image presenter is reached through the main window, so it
        # has no owning tab here: key it by its own capability id.
        flows.append(("export_presenter", flow))
    counts: dict[str, int] = {}
    for session_type, tab in tabs:
        controller = getattr(tab, "_controller", None)
        flow = getattr(getattr(controller, "_save_flow", None), "_flow", None)
        if flow is None:
            continue
        index = counts.get(str(session_type), 0)
        counts[str(session_type)] = index + 1
        flows.append((_unique_key(seen, session_type, index), flow))
    return flows


def _toast_view(window: Any, task_id: int) -> tuple[str | None, Any]:
    """``(message, progress)`` of the toast for *task_id*, or ``(None, None)``.

    Reads the toast manager **only if it is already materialized** (the private
    cache, not the property, which would build one). The toolkit toast is the
    app's own export progress surface: its painted bar is the percentage the
    user sees, so it cannot disagree with the UI.
    """
    manager = getattr(window, "_toast_manager", None)
    toasts = getattr(manager, "_toasts", None)
    if not isinstance(toasts, dict):
        return None, None
    toast = toasts.get(task_id)
    if toast is None:
        return None, None
    message = None
    try:
        label = getattr(toast, "message_label", None)
        text = label.text() if label is not None else ""
        message = " ".join(str(text).split()) or None
    except Exception:
        message = None
    progress = None
    try:
        container = getattr(toast, "progress_container", None)
        bar = getattr(toast, "progress_bar", None)
        if bar is not None and container is not None and not container.isHidden():
            progress = round(max(0, min(100, int(bar.value()))) / 100.0, 2)
    except Exception:
        progress = None
    return message, progress


def _export_jobs(window: Any, key: str, flow: Any) -> list[tuple[dict[str, Any], Callable[[], None]]]:
    registry = getattr(flow, "_save_cancellation", None)
    if not isinstance(registry, dict):
        return []
    out: list[tuple[dict[str, Any], Callable[[], None]]] = []
    for task_id, event in sorted(registry.items(), key=lambda pair: str(pair[0])):
        try:
            if event.is_set():
                # Cancel requested: the worker aborts at its next checkpoint and
                # writes nothing, so this is no longer a running job. Never
                # report it as a "cancelling" zombie — the coordinator's own
                # entry lingers until shutdown (see docs/dev/MCP.md § Jobs).
                continue
        except Exception:
            pass
        message, progress = _toast_view(window, task_id)
        row = _row(
            f"export:{key}:{task_id}",
            KIND_EXPORT,
            "running",
            progress,
            message or "export in progress",
        )
        out.append((row, (lambda ev=event: ev.set())))
    return out


# ---------------------------------------------------------------------------
# collection
# ---------------------------------------------------------------------------


def collect(handlers: Any) -> tuple[list[dict[str, Any]], dict[str, tuple[str, Callable[[], None]]]]:
    """``(rows, cancellable_handles)`` for the live app behind *handlers*.

    Never raises: a source that is not there yet contributes nothing, and an
    idle pass is simply absent (an empty list means "nothing is running").
    """
    rows: list[dict[str, Any]] = []
    handles: dict[str, tuple[str, Callable[[], None]]] = {}
    window = getattr(handlers, "_window", None)
    try:
        tabs = list(handlers._tabs())  # type: ignore[attr-defined]
    except Exception:
        tabs = []
    for key, owner in _gallery_owners(tabs):
        try:
            rows.extend(_gallery_jobs(key, owner))
        except Exception:
            continue
    for key, flow in _save_flows(window, tabs):
        for row, cancel in _export_jobs(window, key, flow):
            rows.append(row)
            handles[row["id"]] = (row["kind"], cancel)
    return rows, handles


class JobMethodsMixin:
    """``jobs_list`` / ``jobs_cancel``, mixed into ``ControlHandlers``.

    ``self`` is a ``ControlHandlers`` (``_window`` / ``_tabs`` come from there).
    """

    def jobs_list(self, _params: dict[str, Any]) -> dict[str, Any]:
        rows, _handles = collect(self)
        return {
            "count": len(rows),
            "jobs": [{key: row.get(key) for key in JOB_KEYS} for row in rows],
        }

    def jobs_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        job_id = str(params.get("id") or "")
        if not job_id:
            raise MethodError("jobs_cancel needs an 'id'", "call jobs_list for the current ids")
        rows, handles = collect(self)
        handle = handles.get(job_id)
        if handle is not None:
            kind, cancel = handle
            cancel()
            return {"cancelled": True, "id": job_id, "kind": kind}
        listed = next((row for row in rows if row["id"] == job_id), None)
        if listed is not None:
            kind = listed["kind"]
            if kind in CANCELLABLE_KINDS:
                raise MethodError(
                    f"job {job_id!r} is no longer running",
                    "call jobs_list: an export settles (or is already cancelling)",
                )
            raise MethodError(
                f"cancel is not supported for kind {kind!r}",
                "only exports expose a safe cancel today — the pool, the metrics "
                "pass and the AI pass have no cooperative cancellation "
                "(see docs/dev/MCP.md § Jobs)",
            )
        raise MethodError(
            f"no running job with id {job_id!r}",
            "call jobs_list — ids are per-run and disappear when the job settles",
        )


__all__ = [
    "CANCELLABLE_KINDS",
    "JOB_KEYS",
    "KINDS",
    "KIND_AI_ANALYSIS",
    "KIND_EXPORT",
    "KIND_GALLERY_POOL",
    "KIND_METRICS_PASS",
    "JobMethodsMixin",
    "collect",
]
