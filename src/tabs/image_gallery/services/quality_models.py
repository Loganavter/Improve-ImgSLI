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

            _models = {
                "lpips": piq.LPIPS(),
                "dists": piq.DISTS(),
                # NR overall quality (no reference needed) for camera/batch.
                "brisque": piq.brisque,
            }
            logger.debug("learned quality backend ready (piq)")
        except Exception:
            logger.debug("learned quality backend unavailable", exc_info=True)
            _models = False
    return _models


def available() -> bool:
    """True when the learned backend (torch + piq) is importable."""
    return bool(_load())


def is_photographic(image, *, max_edge: int = 256) -> bool:
    """Cheap local content gate: natural photo vs cartoon/line-art/screenshot.

    Illustrative/synthetic content has large flat regions and a small palette;
    photographs have continuous tone. Used to gate no-reference metrics that are
    only defined for photographic content (BRISQUE). Fail-open: unreadable input
    is treated as photographic (show the metric rather than silently drop it).
    """
    try:
        import numpy as np
        from PIL import Image as _Image

        im = image.convert("RGB")
        w, h = im.size
        m = max(int(w), int(h))
        if m > max_edge > 0:
            scale = max_edge / m
            try:
                resample = _Image.Resampling.BILINEAR  # type: ignore[attr-defined]
            except AttributeError:
                resample = _Image.BILINEAR  # type: ignore[attr-defined]
            im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), resample)
        a = np.asarray(im, dtype=np.float32)
        g = a.mean(2)
        gx = np.abs(np.diff(g, axis=1))
        gy = np.abs(np.diff(g, axis=0))
        grad = np.zeros_like(g)
        grad[:, :-1] = np.maximum(grad[:, :-1], gx)
        grad[:-1, :] = np.maximum(grad[:-1, :], gy)
        flat = float((grad < 6.0).mean())
        palette = len({tuple(v) for v in (a // 24).astype(np.uint8).reshape(-1, 3)})
        # Conservative: only reject when clearly illustrative (big flat areas or
        # a tiny palette), so a real photo is never hidden by accident.
        return not (flat > 0.7 or palette < 180)
    except Exception:
        return True


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


def nr_metrics(image, *, max_edge: int = _LEARNED_MAX_EDGE) -> dict:
    """No-reference overall quality (BRISQUE, lower = better) for one image.

    For camera/batch modes where there is no source to anchor against. Returns
    ``{}`` when the backend is unavailable — fail-open to "not measured".
    """
    models = _load()
    if not models or image is None:
        return {}
    # BRISQUE is trained on natural photos — out of domain on cartoon/line-art/
    # screenshot (it rates grain as "natural"). Gate it by content type.
    if not is_photographic(image):
        return {}
    try:
        import torch

        w, h = image.size
        m = max(int(w), int(h))
        if m > max_edge > 0:
            scale = max_edge / m
            size = (max(1, int(w * scale)), max(1, int(h * scale)))
        else:
            size = (max(1, int(w)), max(1, int(h)))
        # BRISQUE operates on the 0-255 scale.
        t = _tensor(image, size) * 255.0
        with torch.no_grad():
            value = float(models["brisque"](t, data_range=255.0).item())
        return {"brisque": value} if value == value else {}
    except Exception:
        logger.debug("nr_metrics failed", exc_info=True)
        return {}
