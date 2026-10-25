"""Learned perceptual metrics (LPIPS / DISTS / BRISQUE) for fidelity ranking.

Standard-benchmark validation (BAPPS 2AFC, chance 50 %) showed learned metrics
clearly beat our shallow ones for "which variant is closest to the source":

    set          L2    SSIM   LPIPS   DISTS
    traditional  55.4  59.9   73.4    77.2
    cnn          79.5  79.2   82.2    82.2
    superres     65.4  64.6   69.5    71.0

The backend (`torch` + `piq`) is a **hard runtime requirement**, pinned in
`requirements-gui.txt`. LPIPS + DISTS (reference) and BRISQUE (no-reference) are
the "learned trio" the gallery ranker measures, so absence is an **explicit,
queryable state** — `backend_status()` returns ``"ready"`` / ``"missing"`` /
``"error"`` with `backend_reason()` — never a silent "report unchanged".
Ranking consumers must consult the status (or call `require_backend()`, which
fails closed) rather than reading an empty `pair_metrics()` / `nr_metrics()`
result as "measured, nothing found".

Two orthogonal gates — do not conflate them:

- **Availability** (can torch/piq be loaded?) is global and fail-closed; a
  missing backend is a visible state for the whole ranking path.
- **Applicability** (does BRISQUE make sense for this content?) is per-image:
  BRISQUE is trained on natural photographs and is out of domain on
  cartoon/line-art/screenshot, so `nr_metrics()` still content-gates it via
  `is_photographic()`. That is a *content* gate, **not** an availability gate
  (the backend may be perfectly ready and BRISQUE still be skipped).

Import discipline: the backend is imported **lazily, inside the quality worker
path** — the single seam `_import_backend()` — never at module import and never
at Qt/app init, because torch + PySide6 sharing OpenMP can segfault at teardown
(see the internal-docs `inv-gallery-learned-metrics` investigation). This module
must stay importable with the backend absent.

Pure (no Qt); the models are a process singleton guarded by a lock, so this is
safe to call from the Stage-2 worker threads. Cost is bounded by capping the
longest edge before the forward pass.
"""

from __future__ import annotations

import logging
import threading
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Learned metrics are somewhat scale-sensitive; a fixed cap keeps the ranking
#: stable across items and bounds CPU cost in the background worker.
_LEARNED_MAX_EDGE = 512

_lock = threading.Lock()
#: None = not tried yet; False = backend unavailable; dict = {name: model}.
_models: dict | bool | None = None
#: The ``torch`` module resolved by the backend import (a fake in tests).
_torch_mod = None
#: Explicit availability state: "ready" | "missing" | "error" (None = unknown).
_status: str | None = None
#: Human-readable reason when the backend is not ready (None when ready).
_reason: str | None = None


def _import_backend():
    """Import the learned backend (``piq`` + ``torch``) — the single heavy seam.

    Split out so tests can inject a fake backend. This is the ONLY import site
    for torch/piq and it is reached lazily from the quality worker path, never
    at module import or Qt/app init (torch + PySide6 OpenMP teardown segfault).
    """
    import piq  # type: ignore
    import torch  # type: ignore

    return piq, torch


def _load() -> dict | bool:
    """Lazily import the backend and build the model singletons (once).

    Records an explicit availability state (:data:`_status` / :data:`_reason`)
    rather than failing open silently: ``"missing"`` when torch/piq are not
    installed, ``"error"`` when they are but failed to initialise.
    """
    global _models, _torch_mod, _status, _reason
    if _models is not None:
        return _models
    with _lock:
        if _models is not None:
            return _models
        try:
            piq, torch = _import_backend()

            _models = {
                "lpips": piq.LPIPS(),
                "dists": piq.DISTS(),
                # NR overall quality (no reference needed) for camera/batch.
                "brisque": piq.brisque,
            }
            _torch_mod = torch
            _status, _reason = "ready", None
            logger.debug("learned quality backend ready (piq)")
        except ModuleNotFoundError as exc:
            _models = False
            _status = "missing"
            _reason = str(exc) or "torch/piq not installed"
            logger.debug("learned quality backend missing", exc_info=True)
        except Exception as exc:
            _models = False
            _status = "error"
            _reason = f"{type(exc).__name__}: {exc}"
            logger.debug("learned quality backend failed to load", exc_info=True)
    return _models


def available() -> bool:
    """True when the learned backend (torch + piq) is importable."""
    return bool(_load())


def backend_status() -> str:
    """Explicit learned-backend state: ``"ready"`` | ``"missing"`` | ``"error"``.

    ``missing`` = torch/piq not installed; ``error`` = installed but failed to
    initialise. Both carry a reason via :func:`backend_reason`. Resolves the
    backend on first call, so invoke it from the quality worker/consumer path —
    not at Qt/app init (see the module docstring's import guard).
    """
    if _load():
        return "ready"
    return _status if _status in ("missing", "error") else "missing"


def backend_reason() -> str | None:
    """Human-readable reason the backend is not ready (``None`` when ready)."""
    _load()
    return _reason


class QualityBackendUnavailable(RuntimeError):
    """Raised when a score needs the learned backend but it is not ready."""


def require_backend() -> dict:
    """Return the model singletons, or **fail closed** when the backend is absent.

    Ranking consumers must use this (or check :func:`backend_status`) so a
    missing backend surfaces as an explicit error instead of silently reading
    as an empty measurement.
    """
    models = _load()
    if not models:
        raise QualityBackendUnavailable(backend_reason() or backend_status())
    return models


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


def _torch():
    """The ``torch`` module (from the loaded backend, or imported lazily).

    Kept behind the same lazy seam as :func:`_import_backend`; never imported at
    module load.
    """
    if _torch_mod is not None:
        return _torch_mod
    import torch  # type: ignore

    return torch


def _tensor(image, size):
    """PIL RGB -> [1,3,H,W] float tensor in [0,1], resized to *size*."""
    import numpy as np
    from PIL import Image

    torch = _torch()
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

    Returns ``{}`` when the backend is unavailable or the images are unusable.
    That empty result is *not* self-describing — callers that rank must consult
    :func:`backend_status` / :func:`require_backend` first (fail-closed) so a
    missing backend never reads as "measured, nothing found". Never fabricates a
    constant.
    """
    models = _load()
    if not models or item_image is None or source_image is None:
        return {}
    try:
        torch = _torch()

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
    ``{}`` when the backend is unavailable — an empty result that ranking
    consumers must disambiguate via :func:`backend_status` /
    :func:`require_backend` (fail-closed), not read as "measured, nothing found".
    """
    models = _load()
    if not models or image is None:
        return {}
    # BRISQUE is trained on natural photos — out of domain on cartoon/line-art/
    # screenshot (it rates grain as "natural"). Content gate (applicability),
    # orthogonal to backend availability.
    if not is_photographic(image):
        return {}
    try:
        torch = _torch()

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
