"""QuickLookOverlay theming/translation — veil paint + retranslate + ``_t``.

Moved verbatim from ``ui/quick_look.py`` (plan-gallery-split-2026-10-17,
Part C2). Plain functions taking the overlay as their first argument; the
class keeps same-named one-line delegators. ``super()`` becomes an explicit
``TopLevelInWindowOverlay`` call (the sole base) — same resolution.

``DIM_VEIL_ALPHA`` is the shared mockup value defined in ``labels_theme``
(the file module re-exports its own copy for the shim); the veil fallback
uses the same 0.45·255 literal.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QPainter
from sli_ui_toolkit.widgets import TopLevelInWindowOverlay

from tabs.image_gallery.ui.quick_look.helpers import _set_colored_text
from tabs.image_gallery.ui.quick_look.labels_theme import DIM_VEIL_ALPHA


def _t(self, key: str, default: str) -> str:
    """i18n lookup — EN ``default`` when no translator is wired."""
    tr = getattr(self, "_tr", None)
    if tr is None:
        return default
    try:
        return tr(key, default)
    except Exception:
        return default


def _mode_str_and_fidelity(self) -> tuple[str, bool]:
    """Current report mode string + fidelity flag (shared by populate/retranslate)."""
    mode_str = ""
    try:
        if self._mode is not None:
            mode_str = str(self._mode.value) if hasattr(self._mode, "value") else str(self._mode)
        else:
            mode_str = "fidelity"
        mode_str = mode_str.upper()
        if not mode_str.endswith(" MODE"):
            mode_str = f"{mode_str} MODE"
    except Exception:
        mode_str = "FIDELITY MODE"
    return mode_str, ("FIDELITY" in mode_str)


def retranslate(self, translate=None) -> None:
    """Re-apply keyed chrome after a language switch.

    Re-applies only the flag-dependent toggle labels (Set as
    source/Unset, Reject/Restore), the static Delete label, and the
    report header — a full ``_populate`` would re-decode the preview
    pipeline for a pure text change (W12-A rationale).
    """
    if translate is not None:
        self._tr = translate
    item = getattr(self, "_current_item", None)
    try:
        self._set_source_btn.setVisible(True)
        is_src = (
            self._source_path is not None
            and item is not None
            and Path(getattr(item, "path", "")) == Path(self._source_path)
        )
        if callable(_set_colored_text):
            _set_colored_text(
                self._set_source_btn,
                self._t("image_gallery.quick_look.unset_source", "Unset")
                if is_src
                else self._t("image_gallery.action.set_as_source", "Set as source"),
                None,
            )
    except Exception:
        pass
    try:
        if item is not None and callable(_set_colored_text):
            rejected = bool(getattr(item, "rejected", False))
            _set_colored_text(
                self._reject_btn,
                self._t("image_gallery.quick_look.restore", "Restore")
                if rejected
                else f'✕ {self._t("image_gallery.quick_look.reject", "Reject")}',
                None,
            )
    except Exception:
        pass
    try:
        self._delete_btn.setText(self._t("image_gallery.quick_look.delete", "Delete"))
    except Exception:
        pass
    try:
        mode_str, is_fidelity = self._mode_str_and_fidelity()
        from tabs.image_gallery.ui.quick_look.helpers import populate_report_header

        populate_report_header(self, is_fidelity, mode_str)
    except Exception:
        pass
    # Filename meta line carries the localized size/upscale notes
    # (``mixed sizes`` / ``N upscales of one source`` / ``upscale ×N``);
    # re-render it for the live item so a language switch is not stale.
    # Cheap: dims come from the metrics cache / QImageReader fast path,
    # never a preview decode.
    try:
        if item is not None:
            _, _is_fidelity = self._mode_str_and_fidelity()
            from tabs.image_gallery.ui.quick_look.helpers import populate_filename_meta

            populate_filename_meta(
                self, item, _is_fidelity, getattr(self, "_owner", None)
            )
    except Exception:
        pass
    # The series strip carries translated rank pills (``SOURCE`` / ``★ BEST``)
    # whose text AND fitted width are decided at build. The fingerprint is
    # locale-neutral by design (it tracks the stamped badge, not the rendered
    # one), so the selection-only fast path would keep the previous language —
    # invalidate it and rebuild the strip (thumbs only; no preview decode).
    try:
        self._strip_fingerprint = None
        self._rebuild_strip()
    except Exception:
        pass


def paintEvent(self, event) -> None:  # noqa: N802
    """S4 modal dim veil (mockup fill-opacity 0.45), mirroring clean_review.

    ``TopLevelInWindowOverlay`` paints nothing (transparent background),
    so the veil lives here in gallery scope. The opacity is theme-aware
    (``_dim_veil_alpha``): light keeps the mockup 0.45, dark softens so
    the surroundings do not read as near-black beside the #383838 card.
    """
    try:
        from tabs.image_gallery.ui.quick_look.labels_theme import _dim_veil_alpha

        veil_alpha = _dim_veil_alpha()
    except Exception:
        veil_alpha = DIM_VEIL_ALPHA
    try:
        painter = QPainter(self)
        # No hardcoded QColor (contracts/test_no_hardcoded_qcolor.py):
        # the veil is mockup-specified plain black at an opacity, not
        # a theme color — Qt global black + painter opacity.
        painter.setOpacity(veil_alpha / 255.0)
        painter.fillRect(self.rect(), QBrush(Qt.GlobalColor.black))
        painter.end()
    except Exception:
        pass
    try:
        # Chrome painted: a cold-open canvas staged in populate may show.
        if getattr(self, "_preview_canvas_pending", None) is not None:
            try:
                from tabs.image_gallery.debug import ql_cover as _qlc
                from tabs.image_gallery.debug import ql_cover_enabled as _qlc_on

                if _qlc_on():
                    _qlc("overlay paintEvent pending canvas -> reveal")
            except Exception:
                pass
            from tabs.image_gallery.ui.quick_look.preview_canvas_host import (
                reveal_pending_preview_canvas,
            )

            reveal_pending_preview_canvas(self)
        self._ql_chrome_painted = True
    except Exception:
        pass
    TopLevelInWindowOverlay.paintEvent(self, event)
