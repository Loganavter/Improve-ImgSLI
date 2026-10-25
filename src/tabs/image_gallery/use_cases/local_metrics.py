"""Local Stage-2 cache glue: persist each delivery, hydrate each known item.

Extracted from ``use_cases/proxy_pass`` when the persistence wiring pushed that
module over the file-size gate: the pass' decide/deliver seams stay there, this
module owns the **durable** half of the same seam — and nothing else.

The split is a behaviour boundary, not a taste one:

* ``persist(owner, result, wanted, ...)`` — write what one delivered chunk
  measured (``services/metrics_cache``) under the identity the pass RAN with;
* ``hydrate(owner, items, source, mode)`` — fill every item the store already
  knows and return the MISSES, which are the only items the caller may send to
  the detector pass (a wholly known folder therefore runs zero detectors);
* ``apply_hydrated`` — replay a hit through the LIVE apply tails
  (``_apply_artifact_map`` / ``_apply_fidelity_map`` / ``_apply_camera_map``),
  so a cache hit cannot drift from a cold run: same per-lane filtering, same
  batched repaint, same quick-look refresh, no second apply rule.

Fail-closed rules that live here, not in the store: an item that already carries
local numbers is never "re-hydrated" (in-run state wins), an entry produced under
a previous mode is not persisted (the chunk predates the switch), and the
version-bump invalidation is announced through the EXISTING re-analysis
affordance — the local activity badge the pass itself stamps — never a new
dialog.

INTERFACE: ``kill_switch_flags``, ``pass_full_res_artifacts``, ``identity_for``,
``has_local_state``, ``apply_hydrated``, ``hydrate``, ``persist``.
"""

from __future__ import annotations

import logging

from tabs.image_gallery.debug import gallery_artifacts_disabled as _artifacts_disabled
from tabs.image_gallery.debug import gallery_camera_disabled as _camera_disabled
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_fidelity_disabled as _fidelity_disabled
from tabs.image_gallery.models import ActivityPhase, Mode
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def kill_switch_flags() -> dict:
    """The Stage-2 lane kill-switches, as the store's identity mapping."""
    try:
        return {
            "artifacts": bool(_artifacts_disabled()),
            "fidelity": bool(_fidelity_disabled()),
            "camera": bool(_camera_disabled()),
        }
    except Exception:
        return {}


def pass_full_res_artifacts() -> bool:
    """The artifact lane the Stage-2 pass requests (artifacts on = full-res catalog).

    Mirrors ``proxy_pass._start_proxy_analysis``: it passes
    ``full_res_artifacts=want_artifacts``, so the stored identity must record the
    same flag or a hit would replay proxy severities as tiled ones.
    """
    try:
        return not _artifacts_disabled()
    except Exception:
        return True


def identity_for(item, source, mode, *, full_res_artifacts: bool) -> dict:
    """The fail-closed identity of *item*'s local Stage-2 result (the store's)."""
    from tabs.image_gallery.services.metrics_cache import local_metrics_identity

    return local_metrics_identity(
        getattr(item, "path", None),
        getattr(item, "mtime_ns", None),
        source_path=source,
        mode=mode,
        full_res_artifacts=full_res_artifacts,
        kill_switch=kill_switch_flags(),
    )


def has_local_state(item) -> bool:
    """True when *item* already carries local-pass numbers (no hydrate needed)."""
    for attr in ("metrics", "artifacts", "analysis_records"):
        try:
            if getattr(item, attr, None):
                return True
        except Exception:
            continue
    return False


def apply_hydrated(owner, hits: dict) -> None:
    """Replay persisted entries through the live apply tails (one repaint batch)."""
    for item in list(getattr(owner.state, "items", ()) or ()):
        try:
            metrics = hits.get(str(item.path))
        except Exception:
            continue
        if metrics is None:
            continue
        try:
            item.analysis_records = tuple(metrics.analysis_records)
        except Exception:
            logger.debug("hydrated records attach failed for %s", item.path, exc_info=True)
    arts = {k: m.entry.get("artifacts") for k, m in hits.items() if "artifacts" in m.lanes}
    maps = {k: m.entry.get("artifact_maps") or {} for k, m in hits.items()}
    fid = {k: m.entry.get("fidelity") for k, m in hits.items() if "fidelity" in m.lanes}
    cam = {k: m.entry.get("camera") for k, m in hits.items() if "camera" in m.lanes}
    try:
        if arts:
            owner._apply_artifact_map(arts, maps)
        if fid:
            owner._apply_fidelity_map(fid)
        if cam:
            owner._apply_camera_map(cam)
    except Exception:
        logger.debug("local metrics hydrate apply failed", exc_info=True)


def hydrate(owner, items, source, mode, *, full_res_artifacts=None) -> list:
    """Fill every KNOWN item from the durable store; return the items that MISSed.

    A hit costs one small JSON read — no decode, no detector. Items already
    carrying local numbers (in-run) are neither hits nor misses.
    """
    from tabs.image_gallery.services import metrics_cache as store

    if full_res_artifacts is None:
        full_res_artifacts = pass_full_res_artifacts()
    hits: dict = {}
    misses: list = []
    for item in items:
        if has_local_state(item):
            continue
        try:
            identity = identity_for(
                item, source, mode, full_res_artifacts=full_res_artifacts
            )
            metrics = store.load_local_metrics(identity)
        except Exception:
            metrics = None
        if metrics is None:
            misses.append(item)
            continue
        try:
            hits[str(item.path)] = metrics
        except Exception:
            continue
    if hits:
        apply_hydrated(owner, hits)
    try:
        dropped = int(store.take_invalidation())
    except Exception:
        dropped = 0
    if dropped:
        # A pipeline/payload version bump threw the persisted pass away. Announce
        # it through the EXISTING re-analysis affordance — the local activity
        # badge the pass itself stamps — not a new dialog or new copy.
        try:
            owner._mark_local_pass(list(items), ActivityPhase.ANALYZING)
        except Exception:
            logger.debug("local metrics invalidation badge failed", exc_info=True)
    return misses


def persist(
    owner,
    result: dict,
    wanted,
    *,
    source=None,
    include_camera: bool | None = None,
    full_res_artifacts: bool = False,
) -> None:
    """Write each delivered entry to the durable store (best effort, never raises).

    The identity inputs are the ones the pass RAN with: the captured source, the
    full-res flag and the current mode — and its camera lane. A mode switch while
    a chunk was in flight means the entry describes the previous mode, so it is
    not persisted (a later reopen would otherwise read a camera-less entry as a
    camera-mode measurement).
    """
    from tabs.image_gallery.services import metrics_cache as store

    try:
        mode = getattr(owner.state, "mode", None)
        camera_now = bool(mode == Mode.CAMERA)
    except Exception:
        return
    if camera_now != bool(include_camera):
        _dbg("local metrics: chunk from a previous mode, not persisted")
        return
    by_path = {}
    try:
        for item in list(getattr(owner.state, "items", ()) or ()):
            by_path[str(item.path)] = item
    except Exception:
        return
    lanes = set(wanted or ())
    for key, entry in result.items():
        item = by_path.get(str(key))
        if item is None:
            continue
        try:
            metrics = store.LocalMetrics.from_entry(entry, lanes=lanes)
            if metrics is None:
                continue
            identity = identity_for(
                item, source, mode, full_res_artifacts=full_res_artifacts
            )
            store.save_local_metrics(identity, metrics)
        except Exception:
            logger.debug("local metrics persist failed for %s", key, exc_info=True)
