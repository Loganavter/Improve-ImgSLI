"""Dots helpers — severity tokens & per-dot colors (painter pipeline only)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem

# S2-12: colors via ThemeManager tokens per THEMING.md; fallback hex kept for offscreen tests
_SEVERITY_TOKEN_FALLBACKS: dict[str, tuple[str, str]] = {
    "clean": ("gallery.status.ok", "#3fbf5f"),
    "mild": ("gallery.status.warn", "#e8b64c"),
    "flagged": ("gallery.status.danger", "#D93025"),
}
# Light-theme counterparts of the dark fallbacks above (themes.json light section).
_SEVERITY_FALLBACKS_LIGHT: dict[str, str] = {
    "clean": "#2e7d32",
    "mild": "#b77900",
    "flagged": "#c0392b",
}
_ERROR_LINE_TOKEN_FALLBACK = ("gallery.status.danger", "#D93025")
_ERROR_LINE_FALLBACK_LIGHT = "#c0392b"
_ACCENT_TOKEN_FALLBACK = ("gallery.accent.bar", "#0096FF")
_ACCENT_FALLBACK_LIGHT = "#0078D4"

_DOTS_TEXT = "● ● ●"
_DOTS_ROW_GAP = 2  # RowsContent.row_gap default (compact layout)


def _is_dark() -> bool:
    """Current theme darkness for fallback selection (Rule A).

    Keyed ONLY on ``ThemeManager.is_dark()``: a bare manager defaults to
    ``_current_theme='light'`` (``is_dark()`` False), and an
    empty/unregistered palette does NOT imply dark. Callers
    (``stats_strip``, ``grid_view``, ``hover``) delegate here, so every
    ``_fallback_for(light, dark)`` pair resolves light under a bare manager —
    same as the ``_is_dark_theme`` chains in ``toolbar``/``quick_look``.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        return bool(ThemeManager.get_instance().is_dark())
    except Exception:
        # Manager unreachable (no Qt host at all) — mirror the bare-manager
        # default, which is the light theme.
        return False


def _token_color(token: str, fallback_hex: str):
    """Resolve a ThemeManager palette token; fall back when absent."""
    from PySide6.QtGui import QColor

    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        resolved = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if resolved is not None:
            # resolved may be QColor or hex string — normalize to QColor
            return QColor(resolved) if isinstance(resolved, str) else resolved
    except Exception:
        pass
    return QColor(fallback_hex)


def _severity_color(sev: str):
    key = (sev or "clean").lower()
    token, dark_fallback = _SEVERITY_TOKEN_FALLBACKS.get(key, _SEVERITY_TOKEN_FALLBACKS["clean"])
    fallback = dark_fallback if _is_dark() else _SEVERITY_FALLBACKS_LIGHT.get(key, dark_fallback)
    return _token_color(token, fallback)


def _error_line_color():
    """Rejected/error line: ``gallery.status.danger`` → light/dark fallback."""
    token, dark_fallback = _ERROR_LINE_TOKEN_FALLBACK
    fallback = dark_fallback if _is_dark() else _ERROR_LINE_FALLBACK_LIGHT
    return _token_color(token, fallback)


def _accent_color():
    """Badge/underline accent with the frozen chain + light/dark fallback.

    ``gallery.accent.bar`` → ``accent`` → ``#0078D4`` (light) / ``#0096FF`` (dark).
    """
    from PySide6.QtGui import QColor

    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        mgr = ThemeManager.get_instance()
        for tok in ("gallery.accent.bar", "accent"):
            resolved = try_resolve_theme_color(mgr, tok)
            if resolved is not None:
                return QColor(resolved) if isinstance(resolved, str) else resolved
    except Exception:
        pass
    return QColor(_ACCENT_TOKEN_FALLBACK[1] if _is_dark() else _ACCENT_FALLBACK_LIGHT)


def _dots_for_item(item: GalleryItem, mode: object = None) -> tuple[str, tuple[object, ...]]:
    """Stage 2: per-dot three quality dots via artifact severities (design.md:67-83).

    Mode-dependent mapping (fidelity/banding halo blocking etc):
      - fidelity: banding, halo, blocking
      - camera: noise_amplification, chroma_fringing, halo
      - batch_synthetic: over_smoothing, invented_texture, blocking
    Each dot color resolves via theme tokens (S2-12): clean→success,
    mild→warning, flagged→danger (fallback hexes kept for offscreen tests).
    Returns ``(dot_text, tuple[QColor, QColor, QColor])`` for the dots row.
    Fallback when no artifact data: legacy aggregate still maps to single color triple.
    """

    dot_text = _DOTS_TEXT

    def _severity_str(v) -> str:
        try:
            if hasattr(v, "value"):
                return str(v.value).lower()
            return str(v).lower()
        except Exception:
            return "clean"

    def _color_for_severity(s: str):
        s = (s or "clean").lower()
        if s == "flagged":
            return _severity_color("flagged")
        if s == "mild":
            return _severity_color("mild")
        return _severity_color("clean")

    # Normalize mode string.
    try:
        if mode is None:
            mode_str = ""
        elif hasattr(mode, "value"):
            mode_str = str(mode.value).lower()
        else:
            mode_str = str(mode).lower()
    except Exception:
        mode_str = ""
    # Alias handling.
    if mode_str in ("batch", "batch_synthetic", "batch-synthetic", "synthetic"):
        mode_key = "batch_synthetic"
    elif mode_str in ("fidelity", "fidelity_mode"):
        mode_key = "fidelity"
    elif mode_str in ("camera", "camera_mode"):
        mode_key = "camera"
    elif mode_str == "":
        mode_key = "fidelity"
    else:
        mode_key = mode_str if mode_str in ("fidelity", "camera", "batch_synthetic") else "fidelity"

    MODE_ARTIFACTS: dict[str, list[str]] = {
        "fidelity": ["banding", "halo", "blocking"],
        "camera": ["noise_amplification", "chroma_fringing", "halo"],
        "batch_synthetic": ["over_smoothing", "invented_texture", "blocking"],
    }
    artifacts_for_mode = MODE_ARTIFACTS.get(mode_key, MODE_ARTIFACTS["fidelity"])

    # Build normalized artifact severity map (key lower -> severity str).
    sev_map: dict[str, str] = {}
    try:
        arts = getattr(item, "artifacts", None)
        if isinstance(arts, dict) and arts:
            for k, sev in arts.items():
                try:
                    if hasattr(k, "value"):
                        kk = str(k.value).lower()
                    else:
                        kk = str(k).lower()
                    # Normalize enum repr like "Artifact.BANDING" -> banding
                    if "." in kk:
                        kk = kk.split(".")[-1].lower()
                    sev_map[kk] = _severity_str(sev)
                except Exception:
                    continue
        # Fallback also check metrics["artifacts"] for legacy.
        if not sev_map:
            m = getattr(item, "metrics", None)
            if isinstance(m, dict):
                ma = m.get("artifacts")
                if isinstance(ma, dict) and ma:
                    for k, sev in ma.items():
                        try:
                            kk = str(k).lower()
                            if "." in kk:
                                kk = kk.split(".")[-1].lower()
                            sev_map[kk] = _severity_str(sev)
                        except Exception:
                            continue
    except Exception:
        pass

    # If we have per-artifact data, produce per-dot colors.
    if sev_map:
        colors: list[object] = []
        for art_name in artifacts_for_mode:
            sev = sev_map.get(art_name.lower(), "clean")
            # Also try alias without underscore? e.g. over_smoothing vs oversmoothing
            if sev == "clean" and art_name not in sev_map:
                # try alternative key with hyphen/underscore variants
                alt = art_name.replace("_", "")
                for kk, vv in sev_map.items():
                    if kk.replace("_", "").replace("-", "") == alt.replace("_", ""):
                        sev = vv
                        break
            colors.append(_color_for_severity(sev))
        # Ensure exactly 3.
        while len(colors) < 3:
            colors.append(_severity_color("clean"))
        return dot_text, tuple(colors[:3])

    # Fallback legacy aggregate: map overall flagged/mild/clean to triple of same color.
    def _aggregate_color():
        # Previous aggregate logic: flagged -> red, mild -> yellow, clean -> green #3fbf5f.
        # Keep fallback compatible but use new palette.
        severities: list[str] = []
        try:
            arts2 = getattr(item, "artifacts", None)
            if isinstance(arts2, dict) and arts2:
                for sev in arts2.values():
                    severities.append(_severity_str(sev))
            else:
                m2 = getattr(item, "metrics", None)
                if isinstance(m2, dict):
                    ma2 = m2.get("artifacts")
                    if isinstance(ma2, dict) and ma2:
                        for sev in ma2.values():
                            severities.append(_severity_str(sev))
        except Exception:
            pass
        if severities:
            has_flagged = any(s == "flagged" for s in severities)
            has_mild = any(s == "mild" for s in severities)
            if has_flagged:
                return _severity_color("flagged")
            if has_mild:
                return _severity_color("mild")
            return _severity_color("clean")
        # Legacy artifact_level etc.
        outlier = False
        mild_found = False
        try:
            lvl = getattr(item, "artifact_level", None)
            if lvl is None:
                lvl = getattr(item, "metrics", {}).get("artifact_level") if isinstance(getattr(item, "metrics", None), dict) else None
            if _severity_str(lvl) == "flagged":
                outlier = True
            elif _severity_str(lvl) == "mild":
                mild_found = True
        except Exception:
            pass
        try:
            metrics = getattr(item, "metrics", None) or {}
            if isinstance(metrics, dict):
                art = metrics.get("artifact_level")
                if _severity_str(art) == "flagged":
                    outlier = True
                elif _severity_str(art) == "mild":
                    mild_found = True
                sharp = metrics.get("sharpness")
                ssim = metrics.get("ssim")
                if sharp is not None:
                    try:
                        if float(sharp) < 100:
                            outlier = True
                    except Exception:
                        pass
                if ssim is not None:
                    try:
                        if float(ssim) < 0.8:
                            outlier = True
                    except Exception:
                        pass
                mild_vals = [metrics.get("artifact_level"), metrics.get("artifact"), metrics.get("artifact_score")]
                if any(_severity_str(v) == "mild" for v in mild_vals if v is not None):
                    mild_found = True
        except Exception:
            pass
        try:
            a = getattr(item, "artifact", None)
            if _severity_str(a) == "flagged":
                outlier = True
            elif _severity_str(a) == "mild":
                mild_found = True
        except Exception:
            pass
        if outlier:
            return _severity_color("flagged")
        if mild_found:
            return _severity_color("mild")
        return _severity_color("clean")

    agg = _aggregate_color()
    return dot_text, (agg, agg, agg)
