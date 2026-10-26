"""Stage-2 measured-metrics producers (artifacts + fidelity + camera).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
Each lane runs on a ``GenericWorker`` (never UI-blocking), delivers by path
with a folder-generation stale-drop guard, and repaints through the shared
``_refresh_changed_metrics`` tail. The single-pass proxy path
(``use_cases/proxy_pass``) reuses these apply tails; the per-stage entry
points stay working for the legacy callers. The owner keeps the shared
primitives (``_tracked`` / ``_pool_start`` / ``_is_current_folder_gen`` /
``_folder_gen``) and thin delegators keep the method names verbatim.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.debug import gallery_artifacts_disabled as _artifacts_disabled
from tabs.image_gallery.debug import gallery_camera_disabled as _camera_disabled
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_fidelity_disabled as _fidelity_disabled
from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.use_cases.ai_analysis import (
    _analysis_epoch_is_current,
    analysis_epoch as _analysis_epoch,
)
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _run_artifacts_sync(owner, items: list[GalleryItem], source_path: Path | None) -> dict[str, dict]:
    """Pure worker for GenericWorker: analyze 7 artifacts per item."""
    from tabs.image_gallery.services.artifacts import analyze_artifacts

    out: dict[str, dict] = {}
    for it in items:
        try:
            res = analyze_artifacts(it.path, source_path)
            # Store as str -> Severity value string for serialization, but keep Enum
            out[str(it.path)] = res
        except Exception:
            logger.debug("artifact analyze failed for %s", it.path, exc_info=True)
            out[str(it.path)] = {}
    return out


def _start_artifact_analysis(owner, items: list[GalleryItem], source_path: Path | None) -> None:
    if not items:
        return
    if _artifacts_disabled():
        _dbg("artifact analysis skipped (IMGSLI_GALLERY_NO_ARTIFACTS)")
        return
    # Run in background via GenericWorker (never UI-blocking).
    try:
        gen = owner._folder_gen
        aepoch = _analysis_epoch(owner)  # reset barrier token (``cache_reset``)
        worker = GenericWorker(owner._tracked(owner._run_artifacts_sync), list(items), source_path)
        worker.signals.result.connect(
            lambda res, g=gen, a=aepoch: owner._on_artifacts_ready(res, g, aepoch=a)
        )
        worker.signals.error.connect(owner._on_artifacts_error)
        owner._pool_start(worker, 1)
    except Exception:
        logger.debug("artifact worker start failed", exc_info=True)


def _on_artifacts_ready(owner, result: object, gen: int | None = None, *, aepoch: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched — late artifact catalog dropped
    if not _analysis_epoch_is_current(owner, aepoch):
        return  # metrics reset mid-run — pre-reset catalog dropped
    # result: dict[str(path), dict[Artifact, Severity]]
    if not isinstance(result, dict):
        return
    owner._apply_artifact_map(result)


def _apply_artifact_map(owner, result: dict, maps: dict | None = None) -> None:
    """Shared artifact delivery: batched repaint + quick-look refresh."""
    # Batch the card refresh: per-item refresh_card re-sweeps selection
    # over the whole grid (O(N^2) repaints in one delivery → stalled UI
    # thread → compositor busy cursor + dropped quick-look frames at the
    # clean→flagged flip). Items whose severities did not change skip the
    # repaint entirely.
    changed: list = []
    try:
        from tabs.image_gallery.use_cases import quality as _quality
    except Exception:
        _quality = None  # type: ignore[assignment]
    for item in owner.state.items:
        key = str(item.path)
        arts = result.get(key)
        if arts is None:
            continue
        # Localization rides the artifact delivery; store it even when the
        # severities are unchanged (a first analysis after a metric-only
        # rebuild still needs the map).
        if maps is not None:
            try:
                item.artifact_maps = maps.get(key) or {}
            except Exception:
                pass
        if _quality is None:
            continue
        try:
            # Skip repaints when normalized severities did not change.
            if _quality.severities(item) and _quality.artifacts_equal(item, arts):
                continue
        except Exception:
            pass
        try:
            if _quality.set_artifacts(item, arts):
                changed.append(item)
        except Exception:
            logger.debug("artifact apply failed for %s", item.path, exc_info=True)
    if changed:
        try:
            owner.widget.refresh_cards(changed)  # type: ignore[attr-defined]
        except Exception:
            for item in changed:
                try:
                    owner.widget.refresh_card(item)
                except Exception:
                    logger.debug("widget.refresh_card failed for artifact %s", item.path, exc_info=True)
    # Quick look report: if widget has quick look overlay visible, refresh it.
    for item in changed:
                # Widget owns _quick_look_overlay (QuickLookOverlay).
                for attr in ("_quick_look_overlay", "_quick_look", "_quicklook", "_quicklook_overlay"):
                    ql = getattr(owner.widget, attr, None)
                    if ql is not None and hasattr(ql, "refresh_artifacts"):
                        try:
                            ql.refresh_artifacts(item)
                        except Exception:
                            pass
                # Also try generic widget helpers.
                if hasattr(owner.widget, "refresh_quick_look"):
                    try:
                        owner.widget.refresh_quick_look(item)  # type: ignore[attr-defined]
                    except Exception:
                        pass
                if hasattr(owner.widget, "refresh_artifacts_for"):
                    try:
                        owner.widget.refresh_artifacts_for(item)  # type: ignore[attr-defined]
                    except Exception:
                        pass


def _on_artifacts_error(owner, error_info: object) -> None:
    logger.debug("artifact worker error: %r", error_info, exc_info=True)


# -- fidelity metrics (Stage 2 Pass 1b, wave B producer) --------------------


def _start_fidelity_analysis(owner, items: list[GalleryItem], source_path: Path | None) -> None:
    """Background SSIM/HF/ΔE/upscale metrics vs source (GenericWorker).

    Fail-closed: without a source there is nothing to compare against —
    keys stay absent and quick look renders "not measured" rows.
    """
    if not items or source_path is None:
        return
    if _fidelity_disabled():
        _dbg("fidelity analysis skipped (IMGSLI_GALLERY_NO_FIDELITY)")
        return
    try:
        from tabs.image_gallery.services.fidelity_metrics import run_fidelity_sync

        gen = owner._folder_gen
        aepoch = _analysis_epoch(owner)  # reset barrier token (``cache_reset``)
        worker = GenericWorker(owner._tracked(run_fidelity_sync), list(items), source_path)
        worker.signals.result.connect(
            lambda res, g=gen, a=aepoch: owner._on_fidelity_ready(res, g, aepoch=a)
        )
        worker.signals.error.connect(
            lambda err: logger.debug("fidelity worker error: %r", err, exc_info=True)
        )
        owner._pool_start(worker, 1)
    except Exception:
        logger.debug("fidelity worker start failed", exc_info=True)


def _on_fidelity_ready(owner, result: object, gen: int | None = None, *, aepoch: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched — late fidelity metrics dropped
    if not _analysis_epoch_is_current(owner, aepoch):
        return  # metrics reset mid-run — pre-reset metrics dropped
    if not isinstance(result, dict):
        return
    owner._apply_fidelity_map(result)


def _apply_fidelity_map(owner, result: dict) -> None:
    """Shared fidelity delivery: batched repaint + overlay refresh."""
    # Same batching as _on_artifacts_ready: skip items whose 4 keys did
    # not change, refresh the rest with one selection sweep. Optional
    # learned perceptual keys (LPIPS/DISTS) ride along when the backend is
    # installed; absent backend → they are simply not in the entry.
    required = ("ssim", "hf_ratio", "delta_e", "upscale_factor")
    optional = ("clipping_delta", "halo_delta", "chroma_fringe_delta", "lpips", "dists")
    try:
        from tabs.image_gallery.use_cases import quality as _quality
    except Exception:
        _quality = None  # type: ignore[assignment]
    changed: list = []
    for item in owner.state.items:
        try:
            key = str(item.path)
        except Exception:
            continue
        entry = result.get(key)
        if not isinstance(entry, dict):
            continue
        # Identity fail-closed: entry key came from this item's own path;
        # write the 4 keys only when all measured, never a partial copy.
        if not all(k in entry for k in required):
            continue
        if _quality is None:
            continue
        keys = {k: entry[k] for k in required}
        for k in optional:
            if k in entry:
                keys[k] = entry[k]
        try:
            if _quality.set_metrics(item, keys):
                changed.append(item)
        except Exception:
            logger.debug("fidelity apply failed for %s", item.path, exc_info=True)
    # Shared delivery tail: repaint cards + live-refresh an open overlay.
    owner._refresh_changed_metrics(changed, "fidelity")


def _start_camera_metrics_analysis(owner, items: list[GalleryItem]) -> None:
    """Background camera scalars (sharpness/exposure/clipping) — GenericWorker.

    Camera mode only (the report rows exist only there); unreadable items
    land nothing and keep "not measured" rows (fail-closed per item).
    """
    if not items:
        return
    if _camera_disabled():
        _dbg("camera metrics analysis skipped (IMGSLI_GALLERY_NO_CAMERA)")
        return
    try:
        from tabs.image_gallery.services.camera_metrics import run_camera_metrics_sync

        gen = owner._folder_gen
        aepoch = _analysis_epoch(owner)  # reset barrier token (``cache_reset``)
        worker = GenericWorker(owner._tracked(run_camera_metrics_sync), list(items))
        worker.signals.result.connect(
            lambda res, g=gen, a=aepoch: owner._on_camera_metrics_ready(res, g, aepoch=a)
        )
        worker.signals.error.connect(
            lambda err: logger.debug("camera metrics worker error: %r", err, exc_info=True)
        )
        owner._pool_start(worker, 1)
    except Exception:
        logger.debug("camera metrics worker start failed", exc_info=True)


def _refresh_changed_metrics(owner, changed: list, tag: str) -> None:
    """Shared delivery tail: repaint cards + live-refresh an open overlay."""
    if changed:
        try:
            owner.widget.refresh_cards(changed)  # type: ignore[attr-defined]
        except Exception:
            for item in changed:
                try:
                    owner.widget.refresh_card(item)
                except Exception:
                    logger.debug("widget.refresh_card failed for %s %s", tag, item.path, exc_info=True)
    for item in changed:
        try:
            for attr in ("_quick_look_overlay", "_quick_look", "_quicklook", "_quicklook_overlay"):
                ql = getattr(owner.widget, attr, None)
                if ql is not None and hasattr(ql, "refresh_metrics"):
                    try:
                        ql.refresh_metrics(item)
                    except Exception:
                        pass
        except Exception:
            pass


def _on_camera_metrics_ready(owner, result: object, gen: int | None = None, *, aepoch: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched — late camera metrics dropped
    if not _analysis_epoch_is_current(owner, aepoch):
        return  # metrics reset mid-run — pre-reset scalars dropped
    if not isinstance(result, dict):
        return
    owner._apply_camera_map(result)


def _apply_camera_map(owner, result: dict) -> None:
    """Shared camera delivery: merge scalars + repaint + overlay."""
    try:
        from tabs.image_gallery.use_cases import quality as _quality
    except Exception:
        return
    changed: list = []
    for item in owner.state.items:
        try:
            key = str(item.path)
        except Exception:
            continue
        entry = result.get(key)
        if not isinstance(entry, dict):
            continue
        try:
            if _quality.set_metrics(item, entry):
                changed.append(item)
        except Exception:
            logger.debug("camera metrics apply failed for %s", item.path, exc_info=True)
    owner._refresh_changed_metrics(changed, "camera")
