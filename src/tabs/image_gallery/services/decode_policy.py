"""Gallery decode policy — one home for gallery decode caps (A4).

Every longest-edge bound the gallery applies before or during a decode lives
here as a named constant; entry points import the constant (keeping their
historic private alias where tests read it) and never restate the literal:

- quick-look preview + cover raster share ``PREVIEW_FULL_DECODE_EDGE``
  (same rule: a full decode above this edge is banned — edge^2 x 4B RAM);
- the canvas-private demand pyramid keeps ``QL_FULL_EDGE_CAP``;
- fidelity scalars keep ``SSIM_MAX_EDGE`` / ``HF_MAX_EDGE`` /
  ``DELTAE_THUMB`` / ``CLIP_MAX_EDGE`` / ``ARTIFACT_MAX_EDGE``;
- the blocking detector keeps ``BLOCKING_MAX_NATIVE_EDGE`` (a native-pixel
  abstention bound, not a downscale cap — deliberately distinct from the
  artifact-measure edge even though the value matches);
- coarse pyramid builds default to ``COARSE_LONG_EDGE``;
- the series-strip thumb fallback reads at ``THUMB_FALLBACK_EDGE``;
- VLM uploads default to ``VLM_DEFAULT_MAX_EDGE_PX`` with
  ``VLM_MAX_EDGE_CHOICES`` as the settings surface.

Proxy bounds stay owned by ``services/proxy.py`` — ``PROXY_MAX_EDGE`` is
imported here for reference only, never redefined (A5 owns those lines).
``SSIM_MAX_EDGE`` intentionally matches ``PROXY_MAX_EDGE`` so the SSIM
engine sees exactly the pixels it would have capped to itself (see the
proxy module docstring); the values are equal but owned separately so a
proxy-cache change cannot silently retune the metric.

Pure + Qt-free (safe for ``GenericWorker``); no Store/EventBus writes.

INTERFACE: ``PREVIEW_FULL_DECODE_EDGE``, ``QL_FULL_EDGE_CAP``,
``SSIM_MAX_EDGE``, ``HF_MAX_EDGE``, ``DELTAE_THUMB``, ``CLIP_MAX_EDGE``,
``ARTIFACT_MAX_EDGE``, ``BLOCKING_MAX_NATIVE_EDGE``, ``COARSE_LONG_EDGE``,
``THUMB_FALLBACK_EDGE``, ``VLM_DEFAULT_MAX_EDGE_PX``,
``VLM_MAX_EDGE_CHOICES``, ``exceeds_edge``, ``fit_scale_for_edge``,
``PROXY_MAX_EDGE`` (re-exported from ``services/proxy.py``).
"""

from __future__ import annotations

# Proxy decode bound — owned by services/proxy.py, re-exported here for
# reference only. Never redefine it here (A5 owns the bound/alias lines).
from tabs.image_gallery.services.proxy import PROXY_MAX_EDGE  # noqa: F401

#: Full QPixmap / full-res decode above this edge is banned (RAM: edge^2 x 4B).
#: Shared by the quick-look preview stash and the transient cover raster.
PREVIEW_FULL_DECODE_EDGE = 2048

#: Canvas-private demand-pyramid full-store bound (disk-backed memmap spill).
QL_FULL_EDGE_CAP = 8192

#: Triage-grade resolution caps (longest edge) for the fidelity scalar engine.
SSIM_MAX_EDGE = 1024
HF_MAX_EDGE = 512
DELTAE_THUMB = 64
CLIP_MAX_EDGE = 512

#: Edge artifacts (halo / chroma fringing) are thin rims — measured near full
#: resolution so a 1-2 px rim is not averaged away by downscaling.
ARTIFACT_MAX_EDGE = 2048

#: Largest native edge ``detect_blocking`` will analyse pixel-for-pixel. The
#: 8-px DCT grid only exists at native resolution — above this edge the
#: detector abstains (honest CLEAN) instead of silently downscaling.
BLOCKING_MAX_NATIVE_EDGE = 2048

#: Default longest edge for bounded coarse pyramid builds (quick-look stash,
#: canvas coarse store).
COARSE_LONG_EDGE = 1024

#: Series-strip thumb scaled-reader fallback (longest edge).
THUMB_FALLBACK_EDGE = 512

#: VLM upload downscale default (0 = send original bytes) + settings choices.
VLM_DEFAULT_MAX_EDGE_PX = 1024
VLM_MAX_EDGE_CHOICES = (0, 512, 768, 1024, 1536, 2048)


def exceeds_edge(width, height, cap_edge) -> bool:
    """True when a valid ``(width, height)`` pair exceeds *cap_edge*.

    Garbage / non-positive dims return False (fail-open for ban checks —
    callers treat unmeasurable sources separately). Never raises.
    """
    try:
        w, h = int(width), int(height)
        cap = int(cap_edge)
    except Exception:
        return False
    try:
        if w <= 0 or h <= 0:
            return False
        return max(w, h) > cap
    except Exception:
        return False


def fit_scale_for_edge(width, height, cap_edge) -> float:
    """Scale factor (<= 1.0) fitting ``(width, height)`` inside *cap_edge*.

    ``min(cap/w, cap/h, 1.0)`` — small sources keep scale 1.0; garbage dims
    return 1.0 (no upscale, never a full-res blow-up). Never raises.
    """
    try:
        w, h = int(width), int(height)
        cap = float(cap_edge)
        if w <= 0 or h <= 0 or cap <= 0:
            return 1.0
        return min(cap / w, cap / h, 1.0)
    except Exception:
        return 1.0
