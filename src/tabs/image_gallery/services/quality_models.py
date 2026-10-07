"""Optional learned perceptual metrics (LPIPS / DISTS) for fidelity ranking.

Standard-benchmark validation (BAPPS 2AFC, chance 50 %) showed learned metrics
clearly beat our shallow ones for "which variant is closest to the source":

    set          L2    SSIM   LPIPS   DISTS
    traditional  55.4  59.9   73.4    77.2
    cnn          79.5  79.2   82.2    82.2
    superres     65.4  64.6   69.5    71.0

This module is **optional and lazy**: if the backend (`torch` + `piq`) is not
installed, every entry point returns an empty result — no import error, no
fabricated value, and the fidelity report is byte-for-byte as before. Install
the backend with `requirements-quality.txt` to enable the learned rows.

Pure (no Qt); the models are a process singleton guarded by a lock, so this is
safe to call from the Stage-2 worker threads. Cost is bounded by capping the
longest edge before the forward pass.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("ImproveImgSLI")

#: Learned metrics are somewhat scale-sensitive; a fixed cap keeps the ranking
#: stable across items and bounds CPU cost in the background worker.
_LEARNED_MAX_EDGE = 512

_lock = threading.Lock()
#: None = not tried yet; False = backend unavailable; dict = {name: model}.
_models: dict | bool | None = None


def _load() -> dict | bool:
    """Lazily import the backend and build the model singletons (once)."""
    global _models
    if _models is not None:
        return _models
    with _lock:
        if _models is not None:
            return _models
        try:
            import piq  # type: ignore

            _models = {"lpips": piq.LPIPS(), "dists": piq.DISTS()}
            logger.debug("learned quality backend ready (piq)")
        except Exception:
            logger.debug("learned quality backend unavailable", exc_info=True)
            _models = False
    return _models


def available() -> bool:
    """True when the learned backend (torch + piq) is importable."""
    return bool(_load())


def _tensor(image, size):
    """PIL RGB -> [1,3,H,W] float tensor in [0,1], resized to *size*."""
    import numpy as np
    import torch
    from PIL import Image

    im = image.convert("RGB")
    if im.size != size:
        try:
            resample = Image.Resampling.BILINEAR  # type: ignore[attr-defined]
        except AttributeError:
            resample = Image.BILINEAR  # type: ignore[attr-defined]
        im = im.resize(size, resample)
    arr = np.asarray(im, dtype=np.float32) / 255.0
    return torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0)


def pair_metrics(item_image, source_image, *, max_edge: int = _LEARNED_MAX_EDGE) -> dict:
    """LPIPS + DISTS (lower = closer) for an item/source pair.

    Returns ``{}`` when the backend is unavailable or the images are unusable —
    fail-open to "not measured", never a fabricated constant.
    """
    models = _load()
    if not models or item_image is None or source_image is None:
        return {}
    try:
        import torch

        w, h = source_image.size
        m = max(int(w), int(h))
        if m > max_edge > 0:
            scale = max_edge / m
            size = (max(1, int(w * scale)), max(1, int(h * scale)))
        else:
            size = (max(1, int(w)), max(1, int(h)))
        src = _tensor(source_image, size)
        itm = _tensor(item_image, size)
        out: dict = {}
        with torch.no_grad():
            out["lpips"] = float(models["lpips"](src, itm).item())
            out["dists"] = float(models["dists"](src, itm).item())
        # NaN/inf guard: drop anything non-finite.
        return {k: v for k, v in out.items() if v == v and v not in (float("inf"), float("-inf"))}
    except Exception:
        logger.debug("learned pair metrics failed", exc_info=True)
        return {}
