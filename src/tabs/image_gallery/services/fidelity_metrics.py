"""Fidelity metrics writer — local Pass-1 numbers for S4 (wave B owns producer+consumer).

Writes ``item.metrics`` keys ``ssim`` / ``hf_ratio`` / ``delta_e`` /
``upscale_factor`` per design.md fidelity mode:

- ``ssim`` in [0, 1] vs source via ``shared/analysis.calculate_ssim``
  (same engine Image Compare shows; triage-grade resolution cap);
- ``hf_ratio = hf_out/hf_in - 1`` (Laplacian-variance HF energy ratio;
  dual-bar marker ``frac = 0.5 - clamp(hf,-1,1)*0.5``, so +0.18 → 0.41);
- ``delta_e >= 0`` (mean per-pixel RGB distance on thumbnails);
- ``upscale_factor: int`` (item long side over source long side, >= 1).

Identity fail-closed: keys are written strictly by ``item.path`` — the apply
helpers verify path equality before touching ``item.metrics`` and never copy
metrics between items. Missing/unreadable files leave keys absent (consumers
render "not measured" rows, never fabricated constants).

Pure + Qt-free (safe for ``GenericWorker``); controller wires the background
run (see ``GalleryController._start_fidelity_analysis``).

INTERFACE (wave B): ``compute_fidelity_metrics``,
``apply_fidelity_metrics``, ``run_fidelity_sync``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger("ImproveImgSLI")

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem

#: Triage-grade resolution caps (longest edge) for the scalar engine calls:
#: same ``calculate_ssim`` engine as Image Compare, capped so a 40-file
#: folder finishes in the background without blocking triage.
_SSIM_MAX_EDGE = 1024
_HF_MAX_EDGE = 512
_DELTAE_THUMB = 64


def _cap_edge(image, max_edge: int):
    """Bilinear downscale so the longest edge <= max_edge (no-op if small)."""
    try:
        w, h = image.size
        m = max(w, h)
        if m > max_edge and m > 0:
            from PIL import Image as _Image

            scale = max_edge / m
            try:
                resample = _Image.Resampling.BILINEAR  # type: ignore[attr-defined]
            except AttributeError:
                resample = _Image.BILINEAR  # type: ignore[attr-defined]
            return image.resize((max(1, int(w * scale)), max(1, int(h * scale))), resample)
    except Exception:
        pass
    return image


def _hf_energy(image) -> float | None:
    """Laplacian-variance high-frequency energy (grayscale, capped)."""
    try:
        import numpy as np

        gray = _cap_edge(image.convert("L"), _HF_MAX_EDGE)
        arr = np.asarray(gray, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[0] < 3 or arr.shape[1] < 3:
            return 0.0
        lap = (
            arr[:-2, 1:-1] + arr[2:, 1:-1] + arr[1:-1, :-2] + arr[1:-1, 2:] - 4.0 * arr[1:-1, 1:-1]
        )
        return float(np.var(lap))
    except Exception:
        logger.debug("fidelity hf_energy failed", exc_info=True)
        return None


def _mean_rgb_distance(item_image, source_image) -> float | None:
    """Mean per-pixel Euclidean RGB distance on small thumbnails (>= 0)."""
    try:
        import numpy as np
        from PIL import Image as _Image

        a = _cap_edge(item_image.convert("RGB"), _DELTAE_THUMB)
        b = _cap_edge(source_image.convert("RGB"), _DELTAE_THUMB)
        w, h = min(a.size[0], b.size[0]), min(a.size[1], b.size[1])
        if w <= 0 or h <= 0:
            return None
        try:
            resample = _Image.Resampling.BILINEAR  # type: ignore[attr-defined]
        except AttributeError:
            resample = _Image.BILINEAR  # type: ignore[attr-defined]
        arr_a = np.asarray(a.resize((w, h), resample), dtype=np.float64)
        arr_b = np.asarray(b.resize((w, h), resample), dtype=np.float64)
        diff = arr_a - arr_b
        return float(np.sqrt(np.sum(diff * diff, axis=2)).mean())
    except Exception:
        logger.debug("fidelity delta_e failed", exc_info=True)
        return None


def compute_fidelity_from_images(
    item_image,
    source_image,
    *,
    item_size: tuple[int, int] | None = None,
    source_size: tuple[int, int] | None = None,
) -> dict:
    """Compute the 4 fidelity keys over already-decoded images (no file I/O).

    Shared proxy entry: pass the ``services/proxy.proxy_for`` bytes (or any
    PIL RGB images). ``item_size`` / ``source_size`` are the ORIGINAL
    full-res (w, h) pairs the upscale factor divides (proxies carry them as
    ``Proxy.size``); when omitted they fall back to the given images' own
    sizes. Returns any measurable subset; empty when nothing measurable
    (fail-closed — callers must not fabricate missing keys).
    """
    from shared.analysis.metrics import calculate_ssim

    out: dict = {}
    if item_image is None or source_image is None:
        return {}
    try:
        iw, ih = tuple(item_size) if item_size else tuple(item_image.size)
    except Exception:
        iw, ih = (0, 0)
    try:
        sw, sh = tuple(source_size) if source_size else tuple(source_image.size)
    except Exception:
        sw, sh = (0, 0)
    # W5: snapshot the PRE-CAP original dimensions here, before any
    try:
        orig_item_size = (iw, ih)
        orig_source_size = (sw, sh)
    except Exception:
        orig_item_size = orig_source_size = (0, 0)
    try:
        ssim_val = calculate_ssim(_cap_edge(item_image, _SSIM_MAX_EDGE), _cap_edge(source_image, _SSIM_MAX_EDGE))
        if ssim_val is not None:
            out["ssim"] = max(0.0, min(1.0, float(ssim_val)))
    except Exception:
        logger.debug("fidelity: ssim failed (images)", exc_info=True)
    try:
        hf_out = _hf_energy(item_image)
        hf_in = _hf_energy(source_image)
        if hf_out is not None and hf_in is not None and hf_in > 1e-9:
            out["hf_ratio"] = float(hf_out / hf_in - 1.0)
    except Exception:
        logger.debug("fidelity: hf_ratio failed (images)", exc_info=True)
    try:
        de = _mean_rgb_distance(item_image, source_image)
        if de is not None and de >= 0:
            out["delta_e"] = float(de)
    except Exception:
        logger.debug("fidelity: delta_e failed (images)", exc_info=True)
    try:
        # W4 item 7: factor by LONG side (portrait-safe), from the PRE-CAP
        # snapshot above (W5). Log both sizes at the read site.
        iw2, ih2 = orig_item_size
        sw2, sh2 = orig_source_size
        liw2, lsw2 = max(iw2, ih2), max(sw2, sh2)
        if lsw2 > 0 and liw2 > 0:
            factor = max(1, int(round(liw2 / lsw2)))
            out["upscale_factor"] = factor
            logger.debug(
                "fidelity upscale: item=%dx%d source=%dx%d long=%d/%d factor=%d (pre-cap)",
                iw2, ih2, sw2, sh2, liw2, lsw2, factor,
            )
    except Exception:
        logger.debug("fidelity: upscale_factor failed (images)", exc_info=True)
    return out


def compute_fidelity_metrics(item_path: Path | str, source_path: Path | str) -> dict:
    """Compute the 4 fidelity keys for one item vs the source (no Qt, no state).

    Returns a dict with any subset of ``ssim`` / ``hf_ratio`` / ``delta_e`` /
    ``upscale_factor`` that could be measured; empty when either file is
    unreadable (fail-closed — callers must not fabricate missing keys).

    Proxy-shared (Phase 1): item + source come from the bounded
    ``services/proxy`` cache — cold path decodes each file once total,
    warm path decodes nothing.
    """
    out: dict = {}
    item_path = Path(item_path)
    source_path = Path(source_path)
    if item_path == source_path:
        # Source vs itself: identity scores, no engine call needed.
        return {"ssim": 1.0, "hf_ratio": 0.0, "delta_e": 0.0, "upscale_factor": 1}
    try:
        from tabs.image_gallery.services.proxy import proxy_for

        try:
            item_proxy = proxy_for(item_path)
            source_proxy = proxy_for(source_path)
        except Exception:
            logger.debug("fidelity: unreadable pair %s vs %s", item_path, source_path, exc_info=True)
            return {}
        if item_proxy is None or source_proxy is None:
            logger.debug("fidelity: unreadable pair %s vs %s", item_path, source_path, exc_info=True)
            return {}
        return compute_fidelity_from_images(
            item_proxy.image,
            source_proxy.image,
            item_size=item_proxy.size,
            source_size=source_proxy.size,
        )
    except Exception:
        logger.debug("fidelity: engine import/open failed for %s", item_path, exc_info=True)
    return out


def apply_fidelity_metrics(item: GalleryItem, source_path: Path | str) -> bool:
    """Measure and write the 4 keys into *this* item only (identity fail-closed).

    Verifies the computed pair matches ``item.path`` before writing; never
    copies another item's keys. Returns True only when all 4 keys were
    written.
    """
    try:
        src = Path(source_path)
    except Exception:
        return False
    try:
        own = Path(getattr(item, "path"))
    except Exception:
        return False
    measured = compute_fidelity_metrics(own, src)
    required = ("ssim", "hf_ratio", "delta_e", "upscale_factor")
    if not all(k in measured for k in required):
        return False
    # Identity gate: write strictly by item.path — re-resolve both sides.
    try:
        if Path(getattr(item, "path")) != own:
            return False
    except Exception:
        return False
    try:
        metrics = getattr(item, "metrics", None)
        if not isinstance(metrics, dict):
            return False
        for k in required:
            metrics[k] = measured[k]
        return True
    except Exception:
        logger.debug("fidelity: apply failed for %s", own, exc_info=True)
        return False


def run_fidelity_sync(items: list, source_path: Path | str) -> dict[str, dict]:
    """Pure worker body for ``GenericWorker``: path-keyed metrics per item.

    Returns ``{str(item.path): {4 keys}}`` for measurable pairs only; the
    controller applies each entry back strictly by path (fail-closed).
    """
    out: dict[str, dict] = {}
    try:
        src = Path(source_path)
    except Exception:
        return {}
    for it in items or []:
        try:
            own = Path(getattr(it, "path"))
        except Exception:
            continue
        try:
            measured = compute_fidelity_metrics(own, src)
        except Exception:
            logger.debug("fidelity: worker compute failed for %s", own, exc_info=True)
            continue
        if all(k in measured for k in ("ssim", "hf_ratio", "delta_e", "upscale_factor")):
            out[str(own)] = {k: measured[k] for k in ("ssim", "hf_ratio", "delta_e", "upscale_factor")}
    return out
