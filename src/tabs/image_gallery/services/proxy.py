"""Shared bounded proxy decodes for gallery Stage-2 analyses.

Phase-1 proxy sharing: artifact + fidelity + camera stages used to fully
decode every image themselves (artifacts opens item+source per item,
fidelity opens item+source per item, camera opens 3x per item — source
re-decoded N times per stage). All three stages now consume one shared
bounded proxy per file (longest edge <= ``PROXY_MAX_EDGE``) built here:

- cold path: ONE full decode per item total; the source decoded ONCE total
  (in-memory cache shared across items and stages);
- warm path (proxy cached): ZERO decodes — ``proxy_for`` serves the cached
  image without touching ``Image.open``.

Fail-closed identity: the cache key is ``(resolved path, mtime_ns, size)``
so an edited file misses and recomputes; proxies are never shared between
different paths. Cached images are read-only inputs — stage entry points
must never mutate or close them (detectors only ``resize``/``convert``,
which return new images).

W12 — one computation, not two: the engine plan runs first and the legacy
Stage-2 dicts are REBUILT from the records' pre-score ``raw`` values, so the
detectors run once per item. That record→dict glue lives in
``services/analysis_bridge.py`` (W14), not here.

P9b — the engine is the ONLY analysis path. The env kill-switch and the
per-stage "engine first, else the legacy detector" fallbacks are gone: when a
stage's records carry no usable number, the entry simply carries no dict for
that stage and one ``warning`` names the stage and the producer. Gaps are the
honest answer; a missing number must stay visibly missing. The ONE retained
fallback is the artifact catalog (``_analyze_artifacts_full_res`` /
``analyze_images`` below), because a missing artifact entry renders as
``clean`` in the UI (``quality_read.domain_artifact_severity``) and a producer
failure would then look like "nothing wrong" instead of a failure.

W14 — one artifact catalog, too: in ``full_res_artifacts`` mode the engine is
handed the SAME full-resolution store the tiled catalog reads, so the records
carry the tiled severities the entry shows instead of proxy ones the read path
would prefer.

Pure + Qt-free (safe for ``GenericWorker``); no Store/EventBus writes.

INTERFACE: ``PROXY_MAX_EDGE``, ``PROXY_CACHE_LIMIT``, ``Proxy``, ``proxy_for``,
``clear_proxy_cache``, ``run_proxy_stages_sync`` (``cancel`` = the preemption
seam). The record→legacy-dict bridge is ``services.analysis_bridge`` (W14); the
artifact catalog fallback (``_analyze_artifacts_full_res``) is the only legacy
stage call this module still makes, and only as that documented exception.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger("ImproveImgSLI")

#: Longest edge of a shared proxy. Matches the fidelity SSIM cap
#: (``services/fidelity_metrics._SSIM_MAX_EDGE``) so the SSIM engine sees
#: exactly the pixels it would have capped to itself; every other consumer
#: caps further down (512 / 64) and is resolution-insensitive past that.
PROXY_MAX_EDGE = 1024

#: Single canonical proxy-cache bound (true LRU, owned here): 96 x <=3MB
#: ~= <=288MB worst-case RSS, matches the controller trim so
#: ``_trim_proxy_cache`` keeps working untouched.
PROXY_CACHE_LIMIT = 96

_PROXY_CACHE_LIMIT = PROXY_CACHE_LIMIT  # backwards-compat alias; single bound owned here.



class Proxy(NamedTuple):
    """One shared bounded decode: RGB pixels + original full-res size."""

    image: object  # PIL.Image.Image in RGB, longest edge <= PROXY_MAX_EDGE
    size: tuple[int, int]  # original (w, h) BEFORE the proxy downscale


_PROXY_CACHE: dict[tuple[str, int, int], Proxy] = {}


def _touch_proxy_entry(key: tuple[str, int, int]) -> None:
    """Mark *key* most-recently-used (plain-dict reorder, no lock — same no-lock discipline as the rest of this module)."""
    try:
        _PROXY_CACHE[key] = _PROXY_CACHE.pop(key)
    except Exception:
        pass


def clear_proxy_cache() -> int:
    """Drop cached proxies. Returns entries cleared (tests)."""
    try:
        n = len(_PROXY_CACHE)
    except Exception:
        return 0
    try:
        _PROXY_CACHE.clear()
    except Exception:
        pass
    return n


def _stat_key(path: Path) -> tuple[str, int, int] | None:
    """Content key for *path*: (resolved, mtime_ns, size); None on miss."""
    try:
        resolved = str(Path(path).resolve())
        st = os.stat(resolved)
        return (resolved, int(getattr(st, "st_mtime_ns", 0)), int(st.st_size))
    except Exception:
        return None


def _build_proxy(path: Path) -> Proxy | None:
    """Decode *path* once, normalize to RGB, downscale to PROXY_MAX_EDGE."""
    try:
        from PIL import Image as _Image
    except Exception:
        return None
    try:
        with _Image.open(path) as im:
            try:
                orig = (int(im.size[0]), int(im.size[1]))
            except Exception:
                orig = (0, 0)
            try:
                rgb = im.convert("RGB")
            except Exception:
                return None
            try:
                w, h = rgb.size
                m = max(w, h)
                if m > PROXY_MAX_EDGE and m > 0:
                    scale = PROXY_MAX_EDGE / m
                    try:
                        resample = _Image.Resampling.BILINEAR  # type: ignore[attr-defined]
                    except AttributeError:
                        resample = _Image.BILINEAR  # type: ignore[attr-defined]
                    rgb = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))), resample)
            except Exception:
                pass
            try:
                rgb.load()
            except Exception:
                pass
            # convert/resize detach from the file handle — safe past close.
            return Proxy(image=rgb, size=orig)
    except Exception:
        logger.debug("proxy: decode failed for %s", path, exc_info=True)
        return None


def proxy_for(path: Path | str) -> Proxy | None:
    """Shared bounded proxy for *path* (cached; None when unreadable).

    Cold: exactly one ``Image.open`` for a readable file. Warm: no decode
    at all — the cached proxy is returned as-is (callers must not mutate
    or close it).
    """
    try:
        p = Path(path)
    except Exception:
        return None
    key = _stat_key(p)
    if key is None:
        return None
    try:
        hit = _PROXY_CACHE.get(key)
    except Exception:
        hit = None
    if hit is not None:
        _touch_proxy_entry(key)
        return hit
    proxy = _build_proxy(p)
    if proxy is None:
        return None
    try:
        while len(_PROXY_CACHE) >= PROXY_CACHE_LIMIT:
            try:
                oldest = next(iter(_PROXY_CACHE))
            except StopIteration:
                break
            try:
                del _PROXY_CACHE[oldest]
            except Exception:
                break
        _PROXY_CACHE[key] = proxy
    except Exception:
        pass
    return proxy


def _open_full_res_store(path):
    """One full-resolution ``TiledPixelStore`` for *path*, or ``None`` on failure.

    Wave A3: the caller owns ``close()`` (the store deletes a disk spill on
    close). Any decode/size/pyvips failure is swallowed — the callers
    fail open to the bounded proxy.
    """
    try:
        from engine.store.tiled_pixel_store import TiledPixelStore

        return TiledPixelStore.from_path(path)
    except Exception:
        logger.debug("proxy batch: full-res store open failed for %s", path, exc_info=True)
        return None


def _analyze_artifacts_full_res(own, source_store, same, proxy_image, src_img):
    """Tiled full-res artifact catalog with per-item fail-open to the proxy.

    Builds one full-resolution store for *own*, runs
    ``analyze_artifacts_tiled`` over it (anchored on *source_store* unless
    this is the same-file pair, which stays sourceless), closes the store in
    a ``finally`` and falls back to ``analyze_images(proxy_image, src_img)``
    on any error. Never raises.

    This (and the ``analyze_images`` call beside it in
    ``run_proxy_stages_sync``) is the ONE legacy stage call P9b kept: the
    artifact catalog is all-or-nothing in the UI and a missing entry renders as
    ``clean``, so recomputing it is the difference between a visible flag and a
    silent "nothing wrong".
    """
    from engine.store.tiled_pixel_store import TiledPixelStore
    from tabs.image_gallery.services.artifact_tiles import analyze_artifacts_tiled
    from tabs.image_gallery.services.artifacts import analyze_images

    item_store = None
    try:
        item_store = TiledPixelStore.from_path(own)
        source_image = None if same else source_store
        return analyze_artifacts_tiled(item_store, source_image=source_image)
    except Exception:
        logger.debug("proxy batch: tiled artifacts failed for %s", own, exc_info=True)
        return analyze_images(proxy_image, src_img)
    finally:
        if item_store is not None:
            try:
                item_store.close()
            except Exception:
                logger.debug("proxy batch: item store close failed for %s", own, exc_info=True)


def _warn_stage_without_numbers(own, stage, axes, by_axis, *, warned: set) -> None:
    """One ``warning`` per stage per batch when its records cannot answer (P9b).

    ``analysis_bridge.reportable_gaps`` decides what is worth reporting (a stage
    that lost every axis, or a producer that raised); a plain gap is normal and
    the read path shows it per axis. Deliberately once per stage, not once per
    item: the message names the first item that hit it, so a broken producer
    cannot bury the log in one line per item of the batch.

    There is no legacy call behind this warning any more — the entry simply has
    no numbers for *stage*.
    """
    from tabs.image_gallery.services import analysis_bridge as bridge

    missing = bridge.reportable_gaps(by_axis, axes)
    if not missing or stage in warned:
        return
    warned.add(stage)
    logger.warning(
        "proxy batch: %s records unusable for %s — %s; no legacy fallback "
        "(a gap is the honest answer, the records are the only path)",
        stage,
        own,
        bridge.describe_gaps(missing, by_axis),
    )


def _should_stop(index: int, cancel) -> bool:
    """Pool slice every 2 items (a 50-file chunk is ONE job); stop on ``cancel()``."""
    if not index or index % 2:
        return False
    time.sleep(0)
    try:
        return bool(cancel()) if cancel is not None else False
    except Exception:
        return False


def run_proxy_stages_sync(
    items: list,
    source_path: Path | str | None,
    cancel=None,
    *,
    include_camera: bool = False,
    full_res_artifacts: bool = False,
) -> dict[str, dict]:
    """Single-pass Stage-2 worker body for ``GenericWorker``.

    Builds each item proxy ONCE and the source proxy ONCE, then produces the
    artifact catalog + fidelity metrics (+ camera scalars when ``include_camera``)
    over the shared bytes from the analysis engine's records (P9b: the engine is
    the ONLY path — no env switch, no per-stage legacy fallback). W12: one
    detector pass, each stage dict rebuilt from its ``raw``; a stage the records
    cannot answer is absent from the entry and warned about once.

    Returns ``{str(item.path): {"artifacts": {...}, "fidelity": {...},
    "camera": {...}}}`` — stage dicts present only when that stage was requested
    and measured (fail-closed per item, path-keyed, never copied between items).
    The controller still owns delivery (wave B).

    ``full_res_artifacts`` (wave A3): run the artifact catalog tiled over a
    full-resolution ``TiledPixelStore`` per item (8x8 block grid, thin chroma
    rims), with ONE ``source_store`` per call; fidelity/camera keep the bounded
    proxy. A store that cannot be opened fails open to the proxy catalog.

    ``cancel`` (optional callable) is the per-item generation check the caller
    owns (``not owner._is_current_folder_gen(gen)``); the pass yields every two
    items and stops at the first boundary where it is true.

    That item store is handed to the engine (W14), so records and tiled
    severities are ONE computation; the tiled call still runs when no store
    opened or the records are unusable — the ONE retained fallback (P9b).
    """
    from tabs.image_gallery.services import analysis_bridge as bridge
    from tabs.image_gallery.services.artifacts import analyze_images

    #: Stage warnings fire once per stage per batch, never once per item.
    warned: set[str] = set()

    out: dict[str, dict] = {}
    try:
        src_proxy = proxy_for(source_path) if source_path is not None else None
    except Exception:
        src_proxy = None
    source_store = None
    if full_res_artifacts and source_path is not None:
        source_store = _open_full_res_store(source_path)
    try:
        for index, it in enumerate(items or []):
            # Preemption seam: sleep(0) releases the GIL for a scroll's visible
            # thumbnails; the generation check drops a folder already left.
            if _should_stop(index, cancel):
                logger.debug("proxy batch: stopped at item %d (generation moved)", index)
                break
            try:
                own = Path(getattr(it, "path"))
            except Exception:
                continue
            key = str(own)
            entry: dict = {}
            try:
                proxy = proxy_for(own)
            except Exception:
                proxy = None
            if proxy is None:
                out[key] = entry
                continue
            try:
                src_img = src_proxy.image if src_proxy is not None else None
                same = False
                if src_proxy is not None:
                    try:
                        same = Path(source_path).resolve() == own.resolve()  # type: ignore[arg-type]
                    except Exception:
                        same = False
                    if same:
                        src_img = None  # same-file pair: detectors run sourceless
                # W12/P9b: the engine runs FIRST and is the only path — the
                # stage dicts are rebuilt from its records, one detector pass.
                rebuilt: dict[str, dict] = {}
                records = None
                item_store = None
                # W14: the tiled catalog can only be reproduced when the shared
                # full-resolution source store the legacy call would anchor on is
                # actually open (a source whose store failed stays sourceless in
                # both paths — never anchored on the bounded proxy instead).
                tiled_reproducible = not (
                    full_res_artifacts
                    and source_path is not None
                    and not same
                    and source_store is None
                )
                if full_res_artifacts and tiled_reproducible:
                    item_store = _open_full_res_store(own)
                artifacts_from_records = not full_res_artifacts or item_store is not None
                by_axis: dict = {}
                try:
                    records = bridge.engine_records(
                        own, proxy.image, src_img,
                        tiled_store=item_store,
                        # The full-resolution reference, not the bounded
                        # proxy: tile boxes are item coordinates.
                        tiled_source_store=(
                            source_store if item_store is not None and not same else None
                        ),
                    )
                    by_axis = bridge.records_by_axis(records)
                    if records is not None:
                        try:
                            rebuilt = bridge.stage_dicts_from_records(
                                records, proxy=proxy, source_proxy=src_proxy,
                                same=same, include_camera=include_camera,
                                # Proxy ranks are not the tiled severities the
                                # entry shows: only rebuild artifacts from
                                # records that measured the tiled store.
                                artifacts_from_records=artifacts_from_records,
                            )
                        except Exception:
                            # A rebuild failure is a hole in every rebuilt stage:
                            # P9b keeps no legacy call behind it, so say so.
                            logger.warning(
                                "proxy batch: record rebuild failed for %s — the "
                                "entry carries no rebuilt stage dicts",
                                own, exc_info=True,
                            )
                finally:
                    if item_store is not None:
                        try:
                            item_store.close()
                        except Exception:
                            logger.debug(
                                "proxy batch: item store close failed for %s", own, exc_info=True
                            )
                if "artifacts" in rebuilt:
                    entry["artifacts"] = rebuilt["artifacts"]
                else:
                    # THE ONE RETAINED LEGACY FALLBACK (P9b). Deliberately NOT
                    # the camera/fidelity rule: an absent artifact entry renders
                    # as ``clean`` (``quality_read.domain_artifact_severity``),
                    # so a producer failure would look like "nothing wrong" —
                    # the catalog is recomputed over the same pixels. Every other
                    # stage stays a gap: a missing number is visibly missing.
                    if records is None or artifacts_from_records:
                        _warn_stage_without_numbers(
                            own, "artifacts", bridge.ARTIFACT_AXES, by_axis, warned=warned
                        )
                    else:
                        logger.debug(
                            "proxy batch: artifact records are not the tiled catalog for %s", own
                        )
                    if full_res_artifacts:
                        entry["artifacts"] = _analyze_artifacts_full_res(
                            own, source_store, same, proxy.image, src_img
                        )
                    else:
                        entry["artifacts"] = analyze_images(proxy.image, src_img)
            except Exception:
                logger.warning(
                    "proxy batch: stage assembly failed for %s — the entry carries "
                    "no artifacts/fidelity/camera numbers", own, exc_info=True
                )
            # Coarse localization for the artifacts that actually fired (SalArt-VQA:
            # tie a claim to local evidence). Only non-clean axes, so the tile pass
            # stays cheap; failures leave no map. Runs over the artifacts dict
            # whatever built it (engine records or the catalog fallback).
            try:
                from tabs.image_gallery.services.artifact_maps import localize as _localize

                maps: dict = {}
                for art, sev in (entry.get("artifacts") or {}).items():
                    sv = str(getattr(sev, "value", sev)).lower()
                    if sv == "clean":
                        continue
                    m = _localize(proxy.image, art, src_img, grid=5)
                    if m is not None:
                        maps[str(getattr(art, "value", art))] = m
                if maps:
                    entry["artifact_maps"] = maps
            except Exception:
                logger.debug("proxy batch: localization failed for %s", own, exc_info=True)
            if "fidelity" in rebuilt:
                entry["fidelity"] = rebuilt["fidelity"]
            elif source_path is not None and src_proxy is not None:
                if same:
                    # Same-file pair: identity scores are definitional (no
                    # measurement, no detector) — mirrors
                    # ``compute_fidelity_metrics``' path equality, so it is not
                    # a legacy fallback and keeps no producer alive.
                    entry["fidelity"] = {"ssim": 1.0, "hf_ratio": 0.0, "delta_e": 0.0, "upscale_factor": 1}
                else:
                    # P9b: no fidelity numbers behind a gap. The read path shows
                    # the gap; recomputing the pair here is exactly what this
                    # wave deleted.
                    _warn_stage_without_numbers(
                        own, "fidelity", bridge.FIDELITY_AXES, by_axis, warned=warned
                    )
            if "camera" in rebuilt:
                entry["camera"] = rebuilt["camera"]
            elif include_camera:
                # P9b: no camera numbers behind a gap, for the same reason.
                _warn_stage_without_numbers(
                    own, "camera", bridge.CAMERA_AXES, by_axis, warned=warned
                )
            if records is not None:
                # Per-axis provenance for the read path (W9) — additive, and only
                # when the engine produced records (an item whose engine hook
                # failed has no key, and the read path shows its gaps).
                entry["analysis"] = records
            out[key] = entry
    finally:
        if source_store is not None:
            try:
                source_store.close()
            except Exception:
                logger.debug("proxy batch: source store close failed", exc_info=True)
    return out
