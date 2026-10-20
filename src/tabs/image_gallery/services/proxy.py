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

W12 — one computation, not two: with ``IMGSLI_ANALYSIS_ENGINE=1`` the engine
plan runs first and the legacy Stage-2 dicts are REBUILT from the records'
pre-score ``raw`` values (unreproducible stage ⇒ its legacy call), so the
detectors run once per item; flag off is untouched.

Pure + Qt-free (safe for ``GenericWorker``); no Store/EventBus writes.

INTERFACE: ``PROXY_MAX_EDGE``, ``PROXY_CACHE_LIMIT``, ``Proxy``,
``proxy_for``, ``clear_proxy_cache``, ``run_proxy_stages_sync``,
``ENGINE_FLAG``.
"""

from __future__ import annotations

import logging
import os
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


#: Env flag of the analysis engine (plan-gallery-analysis-engine-2026-10-20 P1).
ENGINE_FLAG = "IMGSLI_ANALYSIS_ENGINE"

#: Engine axis id -> the raw key its legacy stage dict uses, for the three axes
#: whose detector key is not the axis id — the entry is consumed by KEY
#: (``metrics_stage2`` needs ``hf_ratio``/``delta_e``, the report ``clipping_pct``).
LEGACY_RAW_KEYS = {"clipping": "clipping_pct", "detail_gain": "hf_ratio", "color_accuracy": "delta_e"}

#: The axes each legacy Stage-2 dict carries, in its own order — the legacy
#: SHAPES (``measure_camera_from_image`` + the BRISQUE it appends;
#: ``compute_fidelity_from_images``' deltas + LPIPS/DISTS), not a producer
#: vocabulary: a missing record sends that stage back to its legacy call.
CAMERA_AXES = ("sharpness", "exposure", "clipping", "noise", "white_balance", "brisque")
FIDELITY_AXES = ("ssim", "detail_gain", "color_accuracy", "clipping_delta", "halo_delta",
                 "chroma_fringe_delta", "lpips", "dists")
ARTIFACT_AXES = ("banding", "halo", "blocking", "chroma_fringing", "invented_texture",
                 "noise_amplification", "over_smoothing")


def _raw_dict(by_axis: dict, axes) -> dict | None:
    """``{legacy raw key: pre-score raw}`` of the axes answering ``ok``; None when
    the stage cannot be reproduced (missing/``error`` record, or no ``raw``), so
    the caller runs that one legacy call. A ``gap`` is an answer: it is absent,
    exactly as the legacy dict has no such key."""
    out: dict = {}
    for axis in axes:
        record = by_axis.get(axis)
        if record is None or str(getattr(record, "status", "")) == "error":
            return None
        if str(getattr(record, "status", "")) != "ok":
            continue
        raw = getattr(record, "raw", None)
        if raw is None:
            return None
        out[LEGACY_RAW_KEYS.get(axis, axis)] = float(raw)
    return out


def _artifact_dict(by_axis: dict) -> dict | None:
    """``{Artifact: Severity}`` from the catalog ranks; None if any is missing —
    the legacy catalog always carries all seven flags (clean on error), so a
    gap/error/unranked record cannot be rebuilt from records."""
    from tabs.image_gallery.models import Artifact, Severity

    by_rank = {0.0: Severity.CLEAN, 1.0: Severity.MILD, 2.0: Severity.FLAGGED}
    out: dict = {}
    for axis in ARTIFACT_AXES:
        record = by_axis.get(axis)
        raw = getattr(record, "raw", None)
        if str(getattr(record, "status", "")) != "ok" or raw is None:
            return None
        if float(raw) not in by_rank:
            return None
        out[Artifact(axis)] = by_rank[float(raw)]
    return out


def _upscale_factor(item_proxy, source_proxy) -> int | None:
    """Legacy ``upscale_factor`` (long side item/source) from the ORIGINAL sizes:
    not an axis — no detector measures it, no score maps it — so no record can
    carry it; the arithmetic is ``fidelity_metrics``' own (portrait-safe)."""
    try:
        (iw, ih), (sw, sh) = tuple(item_proxy.size), tuple(source_proxy.size)
        liw, lsw = max(int(iw), int(ih)), max(int(sw), int(sh))
        return max(1, int(round(liw / lsw))) if liw > 0 and lsw > 0 else None
    except Exception:
        return None


def _stage_dicts_from_records(records, *, proxy, source_proxy, same,
                              include_camera, full_res_artifacts) -> dict[str, dict]:
    """The legacy Stage-2 dicts rebuilt from engine records (the W12 dedupe).

    The engine's detector pass is the single computation: what the controller
    applies is read off the records' pre-score ``raw`` instead of re-measured.
    Each stage is rebuilt independently and an unreproducible stage stays OUT of
    the result, so the caller runs only that one legacy call. ``full_res_artifacts``
    is never deduped: the tiled catalog reads a full-resolution store no producer
    may open (plan G11), so its severities are a different computation.
    """
    by_axis: dict = {}
    for record in records or ():
        by_axis.setdefault(str(getattr(record, "axis", "") or ""), record)
    by_axis.pop("", None)
    out: dict[str, dict] = {}
    if not full_res_artifacts and (artifacts := _artifact_dict(by_axis)) is not None:
        out["artifacts"] = artifacts
    if include_camera and (camera := _raw_dict(by_axis, CAMERA_AXES)) is not None:
        out["camera"] = camera
    if source_proxy is not None and not same:
        if (fidelity := _raw_dict(by_axis, FIDELITY_AXES)) is not None:
            factor = _upscale_factor(proxy, source_proxy)
            if factor is not None:
                fidelity["upscale_factor"] = factor
            out["fidelity"] = fidelity
    return out


def _engine_records(own, proxy_image, source_image):
    """Engine records for one item (None when it did not run): the local plan over
    the SAME decoded proxy, feeding the entry's numbers
    (``_stage_dicts_from_records``) and the read path's provenance (W9)."""
    try:
        from engine.analysis.registry import discover
        from engine.analysis.resolver import LOCAL_POLICY, resolve_plan
        from tabs.image_gallery.analysis.context_builder import build_context
        from tabs.image_gallery.analysis.runner import PRODUCERS_PACKAGE, run_plan

        ctx = build_context(own, proxy_image=proxy_image, source_image=source_image)
        resolution = resolve_plan(
            discover(PRODUCERS_PACKAGE), policy=LOCAL_POLICY, capabilities=ctx.capabilities
        )
        records, _journal = run_plan(resolution, {str(own): ctx})
        return records[str(own)]
    except Exception:
        # Deliberate broad except, local to the engine hook: it must not break
        # the batch, and the legacy stages rebuild a complete entry without it
        # (plan G6 is about producer fallbacks, not about this opt-in seam).
        logger.warning(
            "proxy batch: analysis engine hook failed for %s", own, exc_info=True
        )
        return None


def run_proxy_stages_sync(
    items: list,
    source_path: Path | str | None,
    *,
    include_camera: bool = False,
    full_res_artifacts: bool = False,
) -> dict[str, dict]:
    """Single-pass Stage-2 worker body for ``GenericWorker``.

    Builds each item proxy ONCE and the source proxy ONCE, then produces the
    artifact catalog + fidelity metrics (+ camera scalars when ``include_camera``)
    over the shared bytes: from the analysis engine's records when ``ENGINE_FLAG``
    is on (W12 — one detector pass, each stage dict rebuilt from its ``raw``),
    from the legacy stage calls otherwise. Returns ``{str(item.path):
    {"artifacts": {...}, "fidelity": {...}, "camera": {...}}}`` — stage dicts
    present only when that stage was requested and measurable (fail-closed per
    item, path-keyed, never copied between items). The controller still owns
    delivery (wave B).

    ``full_res_artifacts`` (wave A3): when True the artifact catalog runs
    tiled over a full-resolution ``TiledPixelStore`` per item instead of the
    bounded proxy, so the 8x8 block grid and thin chroma rims survive. One
    full-res ``source_store`` is built per call and reused across items;
    fidelity/camera still consume the bounded proxy (inputs unchanged). Any
    per-item failure building/using the full-res store fails open to the
    proxy catalog. Default ``False`` is the unchanged proxy path.
    """
    from tabs.image_gallery.services.artifacts import analyze_images
    from tabs.image_gallery.services.camera_metrics import measure_camera_from_image
    from tabs.image_gallery.services.fidelity_metrics import compute_fidelity_from_images

    out: dict[str, dict] = {}
    try:
        src_proxy = proxy_for(source_path) if source_path is not None else None
    except Exception:
        src_proxy = None
    source_store = None
    if full_res_artifacts and source_path is not None:
        source_store = _open_full_res_store(source_path)
    try:
        for it in items or []:
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
                # W12: with the flag on the engine runs FIRST and the legacy stage
                # dicts are rebuilt from its records — one detector pass per item.
                engine_on = os.environ.get(ENGINE_FLAG) == "1"
                rebuilt: dict[str, dict] = {}
                records = None
                if engine_on:
                    records = _engine_records(own, proxy.image, src_img)
                    if records is not None:
                        try:
                            rebuilt = _stage_dicts_from_records(
                                records, proxy=proxy, source_proxy=src_proxy, same=same,
                                include_camera=include_camera,
                                full_res_artifacts=full_res_artifacts,
                            )
                        except Exception:
                            # The bridge is a compatibility shim: a failure here
                            # means "legacy stages for this item", not a broken entry.
                            logger.debug(
                                "proxy batch: engine rebuild failed for %s", own, exc_info=True
                            )
                if "artifacts" in rebuilt:
                    entry["artifacts"] = rebuilt["artifacts"]
                else:
                    if engine_on and not full_res_artifacts:
                        logger.debug("proxy batch: legacy artifact catalog for %s", own)
                    if full_res_artifacts:
                        entry["artifacts"] = _analyze_artifacts_full_res(
                            own, source_store, same, proxy.image, src_img
                        )
                    else:
                        entry["artifacts"] = analyze_images(proxy.image, src_img)
            except Exception:
                logger.debug("proxy batch: artifacts failed for %s", own, exc_info=True)
            # Coarse localization for the artifacts that actually fired (SalArt-VQA:
            # tie a claim to local evidence). Only non-clean axes, so the tile pass
            # stays cheap; failures leave no map. Runs over the artifacts dict
            # whatever built it (engine records or the legacy catalog).
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
                if engine_on and not same:
                    logger.debug("proxy batch: legacy fidelity pair for %s", own)
                try:
                    if same:
                        # Same-file pair: identity scores, no engine call
                        # (mirrors compute_fidelity_metrics path equality).
                        entry["fidelity"] = {"ssim": 1.0, "hf_ratio": 0.0, "delta_e": 0.0, "upscale_factor": 1}
                    else:
                        entry["fidelity"] = compute_fidelity_from_images(
                            proxy.image,
                            src_proxy.image,
                            item_size=proxy.size,
                            source_size=src_proxy.size,
                        )
                except Exception:
                    logger.debug("proxy batch: fidelity failed for %s", own, exc_info=True)
            if "camera" in rebuilt:
                entry["camera"] = rebuilt["camera"]
            elif include_camera:
                if engine_on:
                    logger.debug("proxy batch: legacy camera scalars for %s", own)
                try:
                    entry["camera"] = measure_camera_from_image(proxy.image)
                except Exception:
                    logger.debug("proxy batch: camera failed for %s", own, exc_info=True)
            if records is not None:
                # Per-axis provenance for the read path (W9) — additive, and only
                # when the flag produced records (the flag-off entry has no key).
                entry["analysis"] = records
            out[key] = entry
    finally:
        if source_store is not None:
            try:
                source_store.close()
            except Exception:
                logger.debug("proxy batch: source store close failed", exc_info=True)
    return out
