"""Quick Look metric theming + localization helpers.

Split out of the former ``ui/quick_look/metrics.py`` (plan-gallery-split-2026-10-17,
Part C2). Bodies moved verbatim; names/signatures unchanged. These are the
colour-token, translator and judgment-domain reads the row builders share.
"""

from __future__ import annotations

from PySide6.QtGui import QColor


def _is_dark_theme() -> bool:
    try:
        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _bars_is_dark

        return bool(_bars_is_dark())
    except Exception:
        pass
    return True


def _token_qcolor(token: str, fallback_hex: str, fallback_dark_hex: str | None = None) -> QColor:
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    if fallback_dark_hex is None:
        return QColor(fallback_hex)
    return QColor(fallback_hex if not _is_dark_theme() else fallback_dark_hex)


def _ql_text(overlay, key: str, default: str, **fmt) -> str:
    """Translate a Quick Look string via the overlay's translator (fail-open).

    ``**fmt`` mirrors ``meta._ql_text``: the EN ``default`` carries the
    ``{n}`` placeholders and the SAME ``.format`` runs on the translated
    string, so a locale may reorder them.
    """
    tr = getattr(overlay, "_tr", None)
    text = default
    if callable(tr):
        try:
            text = str(tr(key, default))
        except Exception:
            pass
    if fmt:
        try:
            text = text.format(**fmt)
        except Exception:
            pass
    return text


def _metric_label(overlay, spec_id: str, default: str) -> str:
    """Localized metric row label (``image_gallery.metric.<id>``)."""
    return _ql_text(overlay, f"image_gallery.metric.{spec_id}", default)


def _overlay_judgment_domain(overlay) -> str:
    """The judgment domain the open report renders for ("algorithms" | "ai").

    Read from the overlay's owner (the gallery widget), the durable authority the
    toolbar switch writes (``state.judgment_domain`` is a transient mirror that
    is wholesale replaced — never read as an authority, plan-gallery-jev-pipeline
    §S1). Unknown/absent falls back to Algorithms.
    """
    try:
        owner = getattr(overlay, "_owner", None)
        domain = getattr(owner, "_judgment_domain", None)
        return "ai" if str(domain or "").strip().lower() == "ai" else "algorithms"
    except Exception:
        return "algorithms"


def _metric_note(overlay, spec_id: str, score: int) -> str:
    """Localized band descriptor for a metric row (``metric_note.<id>.<band>``).

    Fail-open: the English ``fallback_note`` when the key/translator is absent.
    """
    try:
        from tabs.image_gallery.services.metric_scores import (
            fallback_note as _fb,
            score_band as _sb,
        )

        default = _fb(spec_id, score)
        band = _sb(score)
    except Exception:
        return ""
    if not default:
        return ""
    return _ql_text(overlay, f"image_gallery.metric_note.{spec_id}.{band}", default)
