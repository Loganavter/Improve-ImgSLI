"""Durable store for the Image Gallery's LOCAL Stage-2 measurement pass.

The AI/Jev scorecards and the profile pin already persist (``services/ai_cache``,
``jev_cache``, ``profile_cache``), but the LOCAL pass — artifact severities, their
localization maps, the fidelity/camera numbers and the engine records they were
rebuilt from — lived only in memory, so every reopen re-decoded and re-ran every
local detector for every known image (the dominant Stage-2 CPU cost;
``task-gallery-persistent-local-metrics-2026-10-22``).

The contract is ``ai_cache``'s, not a second pattern: a hashed filename **plus**
the identity inside the payload re-validated on load, a payload ``version`` gate,
and **any** read problem degrading to a MISS (``None``) with no migration — a
missing record may cost one re-measure, it may never attach a neighbour's number
to a file. An incomplete identity skips the write (no entry beats an
unvalidatable one).

The identity is FAIL-CLOSED and names everything the pass output depends on
(:func:`local_metrics_identity`): ``path``/``mtime_ns``/``size`` (the file version
measured — ``size`` catches an in-place edit that preserved the mtime); ``source``
+ its mtime/size (the reference the fidelity deltas were anchored on); ``mode``
(decides the camera lane) and ``full_res_artifacts`` (tiled severities vs proxy
ones); ``kill_switch`` (a lane that never ran must not read as a lane that came
back clean); ``pipeline_version`` (the engine's own producer versions). A version
bump invalidates every entry ONCE (:func:`ensure_current_version` logs it, and
the folder re-measures through the existing local-activity badge — no new dialog,
no new user-visible copy).

Not a second AI store: ``ai_cache`` owns the VLM scorecard, this module owns the
local pass, and no other cache's keys change here. Pure stdlib + the engine's
record type: no Qt, no workers, no network.

INTERFACE: ``LOCAL_METRICS_VERSION``, ``LocalMetrics``, ``content_key``,
``local_metrics_identity``, ``load_local_metrics``, ``save_local_metrics``,
``pipeline_version``, ``ensure_current_version``, ``take_invalidation``,
``metrics_cache_dir``, ``clear_local_metrics``, ``clear_all``.
Audit-Meta: pattern=wire-cache reason="one local-metrics contract: the fail-closed identity (10 fields), its payload validator and the entry/record codec that must carry it cannot be split without letting one side drift — the ai_cache precedent (the sibling this store mirrors) carries the same marker for the same reason"

"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Payload format version (STORAGE changes here; :func:`pipeline_version` covers
#: DETECTOR changes).
LOCAL_METRICS_VERSION = 1

#: Entry lanes persisted here (the proxy batch entry's stage keys).
_LANE_KEYS = ("artifacts", "artifact_maps", "fidelity", "camera")

#: Kill-switch lanes (``tabs.image_gallery.debug`` env flags).
KILL_SWITCH_LANES = ("artifacts", "fidelity", "camera")

#: Canonical severities. An unknown stored value is corruption, not ``clean``:
#: ``quality.normalize_severity`` degrades unknown values to ``clean`` (a
#: fail-open rule meant for a REPAINT), which on a cache hit would turn a flagged
#: card clean — the "wrong number" this store must never produce.
_SEVERITIES = ("clean", "mild", "flagged")

_MARKER_NAME = "version.json"

#: Process-wide "the marker was reconciled" flag; tests that change versions
#: reset it to ``False``.
_version_checked = False
#: Entries dropped by a version bump until a caller announces them.
_invalidated = 0


def metrics_cache_dir() -> Path:
    """``<cache root>/gallery_local_metrics`` (created on demand)."""
    from services.io.project_package import _cache_root

    root = Path(_cache_root()) / "gallery_local_metrics"
    root.mkdir(parents=True, exist_ok=True)
    return root


def pipeline_version() -> str:
    """The analysis engine's OWN version of the local detector pipeline.

    Derived from the discovered producer manifests' ``ProducerSpec.version``
    (``src/engine/analysis/contracts.py``): bumping a producer's declared version
    IS the statement "the numbers it emits changed". No second version constant
    is invented; an unreadable registry yields the stable token ``"unknown"``.
    """
    try:
        from engine.analysis.registry import discover
        from tabs.image_gallery.analysis.runner import PRODUCERS_PACKAGE

        specs = discover(PRODUCERS_PACKAGE).producers
        return ",".join(f"{spec.id}@{int(spec.version)}" for spec in specs)
    except Exception:
        logger.debug("local metrics: pipeline version unavailable", exc_info=True)
        return "unknown"


def _drop_entries(directory) -> int:
    """Delete every entry file (never the version marker); returns the count."""
    deleted = 0
    try:
        entries = sorted(Path(directory).glob("*.json"))
    except Exception:
        return 0
    for entry in entries:
        if Path(entry).name == _MARKER_NAME:
            continue
        try:
            Path(entry).unlink()
            deleted += 1
        except OSError:
            logger.debug("local metrics: delete failed for %s", entry, exc_info=True)
    return deleted


def ensure_current_version() -> int:
    """Drop every entry ONCE when the payload/pipeline version changed.

    Returns the number deleted (0 when nothing had to go). The marker is only an
    optimisation + an announcement: every identity carries ``pipeline_version``,
    so a stale entry MISSES even if the marker is unreadable and this never runs.
    Never raises.
    """
    global _version_checked, _invalidated
    if _version_checked:
        return 0
    _version_checked = True
    current = {"payload_version": LOCAL_METRICS_VERSION, "pipeline_version": pipeline_version()}
    try:
        directory = metrics_cache_dir()
        marker = Path(directory) / _MARKER_NAME
        previous = None
        if marker.is_file():
            try:
                previous = json.loads(marker.read_text(encoding="utf-8"))
            except Exception:
                previous = None
        if not isinstance(previous, dict):
            # First run here (or an unreadable marker): nothing to invalidate —
            # the identity gate already refuses foreign entries.
            marker.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")
            return 0
        if all(previous.get(key) == value for key, value in current.items()):
            return 0
        dropped = _drop_entries(directory)
        marker.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")
        _invalidated += dropped
        logger.warning(
            "gallery local-metrics cache invalidated: %s -> %s; %d entr(ies) "
            "dropped, every known image re-measures once",
            previous,
            current,
            dropped,
        )
        return dropped
    except Exception:
        logger.debug("local metrics: version reconciliation failed", exc_info=True)
        return 0


def take_invalidation() -> int:
    """Entries dropped by a version bump since the last call; resets the count.

    The caller announces it through the EXISTING re-analysis affordance (the
    local activity badge the pass itself stamps), not a second notification.
    """
    global _invalidated
    dropped = int(_invalidated)
    _invalidated = 0
    return dropped


# -- identity ---------------------------------------------------------------


def _resolved(path) -> str:
    """Resolved absolute path text (``""`` for an empty path); never raises."""
    if path is None:
        return ""
    try:
        return str(Path(path).resolve())
    except Exception:
        try:
            return str(path)
        except Exception:
            return ""


def _stat_version(path) -> tuple[int | None, int | None]:
    """``(mtime_ns, size)`` of *path*, or ``(None, None)`` when unreadable."""
    try:
        stat = Path(path).stat()
        return int(stat.st_mtime_ns), int(stat.st_size)
    except Exception:
        return None, None


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mode_token(mode) -> str:
    """Stable lowercase mode token (``Mode.CAMERA`` and ``"camera"`` agree).

    ``Mode`` is a ``str``-backed enum, so ``isinstance(mode, str)`` is True for
    the member AND ``str(member)`` is ``"Mode.CAMERA"``: the ``.value`` wins
    whenever one exists, or the same mode would key two entries.
    """
    try:
        value = getattr(mode, "value", None)
        if isinstance(value, str):
            mode = value
    except Exception:
        pass
    try:
        token = str(mode or "").strip().lower()
    except Exception:
        return ""
    return token.split(".", 1)[1] if token.startswith("mode.") else token


def _kill_switch_state(kill_switch=None) -> dict:
    """Canonical ``{lane: bool}`` (missing/unknown = that lane was not disabled)."""
    source = kill_switch if isinstance(kill_switch, dict) else {}
    return {lane: bool(source.get(lane, False)) for lane in KILL_SWITCH_LANES}


def content_key(path, mtime_ns, size) -> str:
    """``sha256("<resolved path>:<size>:<mtime_ns>")[:24]`` — THE file-version key.

    Same shape as ``thumbnail_cache.cache_key_for`` plus ``size`` (the plan's ONE
    content key, ``plan-gallery-persistent-catalog-2026-10-21`` §3.3). Not shared
    with the older caches yet: converting them is a separate wave and this module
    must not change their keys. Raises on unusable input; load/save catch.
    """
    resolved = _resolved(path)
    if not resolved:
        raise ValueError("content_key needs a path")
    return hashlib.sha256(
        f"{resolved}:{int(size)}:{int(mtime_ns)}".encode("utf-8")
    ).hexdigest()[:24]


def local_metrics_identity(
    path,
    mtime_ns=None,
    *,
    size=None,
    source_path=None,
    source_mtime_ns=None,
    source_size=None,
    mode=None,
    full_res_artifacts: bool = False,
    kill_switch=None,
    version=None,
) -> dict:
    """The fail-closed identity of one local Stage-2 result (see the module doc).

    Returns a value and never raises: information that cannot be established
    lands as ``None`` and :func:`_canonical_identity` refuses it, so such an entry
    is neither written nor read.
    """
    if mtime_ns is None or size is None:
        stat_mtime, stat_size = _stat_version(path)
        mtime_ns = stat_mtime if mtime_ns is None else mtime_ns
        size = stat_size if size is None else size
    source = _resolved(source_path)
    if source:
        if source_mtime_ns is None or source_size is None:
            stat_mtime, stat_size = _stat_version(source_path)
            source_mtime_ns = stat_mtime if source_mtime_ns is None else source_mtime_ns
            source_size = stat_size if source_size is None else source_size
    else:
        # "No reference" must key differently from "an unreadable reference".
        source_mtime_ns, source_size = 0, 0
    return {
        "path": _resolved(path),
        "mtime_ns": _int_or_none(mtime_ns),
        "size": _int_or_none(size),
        "source": source,
        "source_mtime_ns": _int_or_none(source_mtime_ns),
        "source_size": _int_or_none(source_size),
        "mode": _mode_token(mode),
        "full_res_artifacts": bool(full_res_artifacts),
        "kill_switch": _kill_switch_state(kill_switch),
        "pipeline_version": pipeline_version() if version is None else str(version),
    }


def _canonical_identity(identity) -> dict | None:
    """Normalize *identity* to the declared shape, or ``None`` when incomplete.

    Runs on BOTH sides (expected identity, stored payload), so the comparison is
    a plain ``==`` over the same normalization: a missing field, a non-mapping or
    a mistyped value is "not this identity".
    """
    if not isinstance(identity, dict):
        return None
    path = _resolved(identity.get("path")) if identity.get("path") else ""
    mtime_ns = _int_or_none(identity.get("mtime_ns"))
    size = _int_or_none(identity.get("size"))
    source = _resolved(identity.get("source")) if identity.get("source") else ""
    source_mtime_ns = _int_or_none(identity.get("source_mtime_ns"))
    source_size = _int_or_none(identity.get("source_size"))
    full_res = identity.get("full_res_artifacts")
    kill_switch = identity.get("kill_switch")
    mode = identity.get("mode")
    version = identity.get("pipeline_version")
    if not path or mtime_ns is None or size is None:
        return None
    if source_mtime_ns is None or source_size is None:
        return None
    if not isinstance(full_res, bool) or not isinstance(mode, str) or version is None:
        return None
    if not isinstance(kill_switch, dict):
        return None
    if any(not isinstance(kill_switch.get(lane), bool) for lane in KILL_SWITCH_LANES):
        return None
    version_text = str(version).strip()
    if not version_text:
        return None
    return {
        "path": path,
        "mtime_ns": mtime_ns,
        "size": size,
        "source": source,
        "source_mtime_ns": source_mtime_ns,
        "source_size": source_size,
        "mode": mode.strip().lower(),
        "full_res_artifacts": full_res,
        "kill_switch": _kill_switch_state(kill_switch),
        "pipeline_version": version_text,
    }


def _cache_path(identity) -> Path:
    """``<content key>-<identity digest>.json``; raises for an incomplete identity."""
    canonical = _canonical_identity(identity)
    if canonical is None:
        raise ValueError("incomplete local-metrics cache identity")
    key = content_key(canonical["path"], canonical["mtime_ns"], canonical["size"])
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return metrics_cache_dir() / f"{key}-{digest}.json"


# -- the persisted value ----------------------------------------------------


def _json_safe(value) -> tuple[bool, object]:
    """``(ok, detached copy)`` — JSON compatibility (no NaN) and no shared refs."""
    try:
        return True, json.loads(json.dumps(value, allow_nan=False))
    except Exception:
        return False, None


def _record_to_payload(record) -> dict | None:
    """One ``AxisValue`` as a plain payload dict (``None`` when unbuildable).

    The payload is deliberately thin: :func:`_record_from_payload` rebuilds the
    frozen ``AxisValue`` through its own constructor, so the ENGINE type remains
    the only place the record invariants live (a gap carrying a value, an ``ok``
    without a number, an echo without a backend are refused there, not here).
    """
    try:
        payload = {
            "axis": str(record.axis),
            "value": record.value,
            "producer": str(record.producer),
            "status": str(record.status),
            "reason": str(record.reason or ""),
            "at": int(record.at or 0),
            "raw": record.raw,
            "provenance": str(record.provenance or ""),
        }
        backend = record.backend
        if backend is not None:
            payload["backend"] = {
                "provider": str(backend.provider),
                "model": str(backend.model),
                "base_url": str(backend.base_url),
                "params": dict(backend.params or {}),
            }
    except Exception:
        return None
    ok, safe = _json_safe(payload)
    return safe if ok else None


def _record_from_payload(payload):
    """One ``AxisValue`` rebuilt from its payload; raises when it is not one."""
    from engine.analysis.contracts import AxisValue, BackendRef

    if not isinstance(payload, dict):
        raise ValueError("a stored analysis record must be a mapping")
    backend = payload.get("backend")
    return AxisValue(
        axis=payload.get("axis", ""),
        value=payload.get("value"),
        producer=payload.get("producer", ""),
        backend=BackendRef(**backend) if isinstance(backend, dict) else None,
        status=payload.get("status", ""),
        reason=payload.get("reason", ""),
        at=payload.get("at", 0),
        raw=payload.get("raw"),
        provenance=payload.get("provenance", ""),
    )


@dataclass(frozen=True)
class LocalMetrics:
    """One persisted local Stage-2 result: the entry's lanes + its engine records.

    ``entry`` is the proxy batch entry's JSON-safe stage lanes (``artifacts`` is a
    ``{name: severity}`` mapping) and ``lanes`` records which keys the run actually
    produced, so a hit replays exactly the entry the live delivery would carry: an
    absent lane stays absent instead of becoming an empty number set.
    """

    entry: dict = field(default_factory=dict)
    analysis_records: tuple = ()
    lanes: frozenset = frozenset()

    @classmethod
    def from_entry(cls, entry, *, lanes=(), records=None) -> "LocalMetrics | None":
        """Parse a proxy batch entry (``None`` when it must not be persisted).

        *lanes* are the stage keys the run was ASKED for: an entry missing one is
        an incomplete run (a failed lane, a superseded folder) and is skipped — a
        hit must never present that hole as "measured and clean". *records*
        defaults to the entry's own ``"analysis"`` key. Refuses non-mappings, an
        entry with no lane, unknown severities, non-JSON values and records the
        engine type refuses.
        """
        if not isinstance(entry, dict):
            return None
        wanted = [lane for lane in _LANE_KEYS if lane in set(lanes or ())]
        if any(lane not in entry for lane in wanted):
            return None
        stages: dict = {}
        for lane in _LANE_KEYS:
            if lane not in entry:
                continue
            value = entry.get(lane)
            if lane == "artifacts":
                if not isinstance(value, dict):
                    return None
                severities: dict = {}
                for name, severity in value.items():
                    token = str(getattr(severity, "value", severity) or "").strip().lower()
                    if token not in _SEVERITIES:
                        return None
                    severities[str(getattr(name, "value", name)).strip().lower()] = token
                value = severities
            ok, safe = _json_safe(value)
            if not ok:
                return None
            stages[lane] = safe
        if not stages:
            return None
        rebuilt: list = []
        for record in (entry.get("analysis") if records is None else records) or ():
            payload = record if isinstance(record, dict) else _record_to_payload(record)
            if not isinstance(payload, dict):
                return None
            try:
                rebuilt.append(_record_from_payload(payload))
            except Exception:
                return None
        return cls(entry=stages, analysis_records=tuple(rebuilt), lanes=frozenset(stages))


# -- read / write -----------------------------------------------------------


def load_local_metrics(identity) -> LocalMetrics | None:
    """The persisted local result for *identity*, or ``None`` (a MISS).

    Fail-closed: another identity, a stale payload version, a truncated or
    hand-edited file, an unknown severity or a record the engine type refuses are
    all MISSES with no migration attempt. Never raises.
    """
    try:
        ensure_current_version()
        cache_path = _cache_path(identity)
    except Exception:
        return None
    if not cache_path.is_file():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        if int(data.get("version", -1)) != LOCAL_METRICS_VERSION:
            return None
        if _canonical_identity(data.get("identity")) != _canonical_identity(identity):
            # The filename says it is ours, the payload does not: a miss.
            return None
        entry = data.get("entry")
        lanes = data.get("lanes")
        records = data.get("analysis")
        if records is None:
            records = []
        if not isinstance(entry, dict) or not isinstance(lanes, list):
            return None
        if not isinstance(records, list):
            return None
        return LocalMetrics.from_entry(entry, lanes=lanes, records=records)
    except Exception:
        logger.debug("gallery local-metrics cache read failed", exc_info=True)
        return None


def save_local_metrics(identity, metrics) -> None:
    """Persist *metrics* under *identity*. Never raises; skips an unusable write.

    The write is staged and renamed, so a crash mid-write leaves the previous
    entry or nothing — both load as a MISS, never as a torn number.
    """
    if not isinstance(metrics, LocalMetrics):
        logger.debug("gallery local-metrics write skipped: not a LocalMetrics")
        return
    try:
        ensure_current_version()
        canonical = _canonical_identity(identity)
        if canonical is None:
            logger.debug("gallery local-metrics write skipped: incomplete identity")
            return
        cache_path = _cache_path(canonical)
    except Exception:
        logger.debug("gallery local-metrics write failed", exc_info=True)
        return
    records = [_record_to_payload(record) for record in metrics.analysis_records]
    if any(record is None for record in records):
        logger.debug("gallery local-metrics write skipped: unbuildable record")
        return
    payload = {
        "version": LOCAL_METRICS_VERSION,
        "identity": canonical,
        "lanes": [lane for lane in _LANE_KEYS if lane in metrics.lanes],
        "entry": metrics.entry,
        "analysis": records,
    }
    tmp = cache_path.with_name(cache_path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
        os.replace(tmp, cache_path)
    except Exception:
        logger.debug("gallery local-metrics write failed", exc_info=True)
        try:
            tmp.unlink()
        except OSError:
            pass


# -- clearing ---------------------------------------------------------------


def clear_local_metrics(path, mtime_ns=None, size=None) -> bool:
    """Delete every identity variant for one file version. Never raises."""
    try:
        if size is None:
            _, size = _stat_version(path)
        key = content_key(path, mtime_ns, size)
        candidates = sorted(Path(metrics_cache_dir()).glob(f"{key}-*.json"))
    except Exception:
        return False
    removed = False
    for candidate in candidates:
        try:
            candidate.unlink()
            removed = True
        except OSError:
            logger.debug("local metrics: delete failed for %s", candidate, exc_info=True)
    return removed


def clear_all() -> int:
    """Delete every persisted local result; returns the count deleted. Never raises."""
    try:
        return int(_drop_entries(metrics_cache_dir()))
    except Exception:
        return 0
