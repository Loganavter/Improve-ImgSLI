"""Per-item camera metrics for the gallery (background worker, never UI-blocking).

Keys match exactly what the quick-look camera report reads
(``ui/quick_look/metrics.py``); absent keys render "not measured" rows:

- ``sharpness``: Laplacian-variance float — the SAME definition as mode
  detection (``services/mode._sharpness`` is reused, not duplicated), so the
  report's ok>100 threshold means the same thing everywhere.
- ``exposure``: mean gray / 255 in [0, 1].
- ``clipping_pct``: percent of pixels at the extremes (<=2 or >=253).

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
    return out


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
