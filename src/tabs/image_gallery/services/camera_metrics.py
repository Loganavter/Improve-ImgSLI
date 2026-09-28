"""Per-item camera metrics for the gallery (background worker, never UI-blocking).

Keys match exactly what the quick-look camera report reads
(``ui/quick_look/metrics.py``); absent keys render "not measured" rows:

- ``sharpness``: Laplacian-variance float — the SAME definition as mode
  detection (``services/mode._sharpness`` is reused, not duplicated), so the
  report's ok>100 threshold means the same thing everywhere.
- ``exposure``: mean gray / 255 in [0, 1].
- ``clipping_pct``: percent of pixels at the extremes (<=2 or >=253).
- ``noise``: flat-area HF / flagged threshold in [0, 1] — anchored to the
  sourceless detector branch (``services/artifacts.detect_noise_amplification``:
  flagged above 7.0, mild above 3.5), so the report's warn>0.5 fires exactly
  at the detector's mild. None when numpy is missing or the image has no
  flat area to judge (fail-closed; the Noise row hides).

Unreadable source → ``{}`` (fail-closed; rows stay "not measured").
Histogram stats come from one ≤512 gray decode; sharpness reuses the mode
helper (second bounded decode, same cost class as the scan itself).
"""

from __future__ import annotations

from pathlib import Path

_MAX_EDGE = 512


def _gray_capped(path: Path):
    """Grayscale image with longest edge capped; None on any miss."""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(path) as im:
            gray = im.convert("L")
            w, h = gray.size
            edge = max(w, h)
            if edge > _MAX_EDGE:
                scale = _MAX_EDGE / edge
                nw, nh = int(w * scale), int(h * scale)
                try:
                    resample = Image.Resampling.BILINEAR  # type: ignore[attr-defined]
                except AttributeError:
                    resample = Image.BILINEAR  # type: ignore[attr-defined]
                gray = gray.resize((max(nw, 1), max(nh, 1)), resample)
            gray.load()
            return gray
    except Exception:
        return None


def measure_camera_metrics(path: Path | str) -> dict[str, float]:
    """Measure camera scalars for *path*; ``{}`` when nothing measurable."""
    try:
        p = Path(path)
    except Exception:
        return {}
    out: dict[str, float] = {}
    try:
        from tabs.image_gallery.services.mode import _sharpness

        sharp = _sharpness(p)
        if sharp is not None:
            out["sharpness"] = float(sharp)
    except Exception:
        pass
    try:
        gray = _gray_capped(p)
        if gray is None:
            return out
        hist = gray.histogram()
        total = sum(hist)
        if total <= 0:
            return out
        mean = sum(i * c for i, c in enumerate(hist)) / total
        out["exposure"] = max(0.0, min(1.0, mean / 255.0))
        extreme = sum(hist[:3]) + sum(hist[-3:])
        out["clipping_pct"] = max(0.0, min(100.0, 100.0 * extreme / total))
    except Exception:
        pass
    try:
        noise = estimate_noise(p)
        if noise is not None:
            out["noise"] = noise
    except Exception:
        pass
    return out


# Sourceless detector anchors (services/artifacts.detect_noise_amplification):
# flat-area HF above 7.0 is flagged, above 3.5 mild.
_NOISE_FLAGGED_HF = 7.0


def estimate_noise(path: Path | str) -> float | None:
    """Scalar noise estimate in [0, 1]; None when it cannot be judged."""
    try:
        from PIL import Image as _Image

        from tabs.image_gallery.services.artifacts import (
            _laplacian as _lap,
        )
        from tabs.image_gallery.services.artifacts import (
            _np as _get_np,
        )
        from tabs.image_gallery.services.artifacts import (
            _to_gray_array as _gray_arr,
        )
    except Exception:
        return None
    try:
        np = _get_np()
        if np is None:
            return None
        with _Image.open(path) as im:
            try:
                im.load()
            except Exception:
                pass
            arr = _gray_arr(im)
        if arr is None:
            return None
        try:
            h, w = arr.shape
        except Exception:
            return None
        if h < 8 or w < 8:
            return None
        gx = np.zeros_like(arr)
        gy = np.zeros_like(arr)
        gx[:, :-1] = np.abs(arr[:, 1:] - arr[:, :-1])
        gy[:-1, :] = np.abs(arr[1:, :] - arr[:-1, :])
        flat = np.maximum(gx, gy) < 12.0
        if int(np.sum(flat)) < 100:
            return None  # textured throughout — nothing flat to judge
        lap = _lap(arr)
        if lap is None:
            return None
        flat_hf = float(np.mean(np.abs(lap[flat])))
        return max(0.0, min(1.0, flat_hf / _NOISE_FLAGGED_HF))
    except Exception:
        return None


def run_camera_metrics_sync(items: list) -> dict[str, dict]:
    """Pure worker entry for GenericWorker: path → camera scalars."""
    out: dict[str, dict] = {}
    for it in items or []:
        try:
            out[str(it.path)] = measure_camera_metrics(it.path)
        except Exception:
            try:
                out[str(it.path)] = {}
            except Exception:
                pass
    return out
