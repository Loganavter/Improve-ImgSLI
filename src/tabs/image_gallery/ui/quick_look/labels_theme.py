"""Quick look labels + theme tokens — plain functions (no owner state).

Mockup-pt Label helpers (``_make_label`` / ``_apply_point_size``) and
theme resolution via ``try_resolve_theme_color`` + light/dark fallback
(contracts/test_no_hardcoded_qcolor.py). Extracted verbatim from
``helpers.py`` per CODE_PATTERNS.md thin owner + ui/.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSizePolicy


def _is_dark_theme() -> bool:
    try:
        from tabs.image_gallery.ui.quick_look.bars import _is_dark_theme as _bars_is_dark

        return bool(_bars_is_dark())
    except Exception:
        pass
    return True


def _theme_color(token: str, fallback: str) -> object:
    """Resolve ThemeManager token with fallback hex via ui.theming wrapper (contract-safe)."""
    try:
        from ui.theming import resolve_theme_color

        from sli_ui_toolkit.managers import ThemeManager

        return resolve_theme_color(ThemeManager.get_instance(), token)
    except Exception:
        try:
            from PySide6.QtGui import QColor

            return QColor(fallback)
        except Exception:
            return None


def _token_color(token: str, fallback: str) -> QColor | None:
    """Resolve a ThemeManager token, falling back to *fallback* hex when absent.

    Goes through the sanctioned ``ui.theming.try_resolve_theme_color`` wrapper
    (contract: manual theming glue lives only in theme infra).
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return QColor(c) if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        return QColor(fallback)
    except Exception:
        return None


def _token_rgba_qcolor(token: str, fallback_rgba: tuple[int, int, int, int]) -> QColor | None:
    """Resolve token via ``try_resolve_theme_color`` with rgba fallback."""
    try:
        from sli_ui_toolkit.managers import ThemeManager

        from ui.theming import try_resolve_theme_color

        c = try_resolve_theme_color(ThemeManager.get_instance(), token)
        if c is not None:
            return c if isinstance(c, QColor) else QColor(c)
    except Exception:
        pass
    try:
        return QColor(*fallback_rgba)
    except Exception:
        return None


def _set_colored_text(btn, text: str, color: QColor | None) -> None:
    """Painter-pipeline text color via ButtonRow color (no QSS, no palette)."""
    try:
        from sli_ui_toolkit.widgets import ButtonRow

        btn.setRows([ButtonRow(text=text, size=None, ratio=1.0, color=color)])
    except Exception:
        try:
            btn.setText(text)
        except Exception:
            pass


# S4 v2 LIGHT mockup-pt sizing (W4 item 1): every quick-look Label renders at
# the mockup's own number as *points* via the UiFont point path
# (``UiFont.resolve(point_size=...)`` — scaled exactly once, no UiScale or
# settings changes). ``Label`` itself accepts only ``pixel_size`` (its
# ``_apply_style`` re-runs on font/scale changes using the pixel value), so
# the point font is applied *after* construction and re-asserted after
# Label's own pixel-based restyle. Theme flips only recolor
# (``Label._on_theme_changed``), so they never clobber the point font.
_POINT_PT_BY_PIXEL = {13: 13, 12: 12, 11: 11.5, 10: 10, 9: 9}


def _apply_point_size(label, pt: int | float, **font_kwargs) -> None:
    """Apply a mockup-pt font to a Label via the UiFont point path.

    Extra ``font_kwargs`` (e.g. ``bold=True``) forward to
    ``UiFont.resolve`` so overrides set via the Label constructor survive.
    """
    try:
        from sli_ui_toolkit.managers import UiFont, UiScale

        ui_font = UiFont.get_instance()
        label.setFont(ui_font.resolve(point_size=float(pt), **font_kwargs))
    except Exception:
        try:
            f = label.font()
            f.setPointSizeF(float(pt))
            if font_kwargs.get("bold") is not None:
                f.setBold(bool(font_kwargs["bold"]))
            label.setFont(f)
        except Exception:
            return
    # Re-assert after Label's own pixel-based _apply_style (wired at Label
    # construction, so it always runs first): font_changed and scale_changed
    # would otherwise revert the point font to the pixel value.
    try:
        import weakref as _wr

        from sli_ui_toolkit.managers import UiFont as _UiFont2, UiScale as _UiScale2

        _ui_font = _UiFont2.get_instance()
        _pt = float(pt)
        _fkw = dict(font_kwargs)
        _ref = _wr.ref(label)
        _conns: list = []

        def _reassert() -> None:
            tgt = _ref()
            if tgt is None:
                for _sig, _slot in list(_conns):
                    try:
                        _sig.disconnect(_slot)
                    except Exception:
                        pass
                _conns.clear()
                return
            try:
                tgt.setFont(_UiFont2.get_instance().resolve(point_size=_pt, **_fkw))
            except Exception:
                pass

        try:
            _conns.append((_ui_font.font_changed, _ui_font.font_changed.connect(_reassert)))
            _scale = _UiScale2.get_instance()
            _conns.append((_scale.scale_changed, _scale.scale_changed.connect(_reassert)))
        except Exception:
            pass
    except Exception:
        pass


def _make_label(text: str = "", parent=None, pixel_size: int = 10, pt=None, **kwargs):
    """Create a toolkit Label with mockup-pt sizing (W4 item 1).

    ``pixel_size`` is kept as the Label fallback; the rendered size is the
    mockup number as points (``pt`` override or ``_POINT_PT_BY_PIXEL``).
    """
    from sli_ui_toolkit.widgets import Label

    lbl = Label(text, pixel_size=pixel_size, parent=parent, **kwargs)
    try:
        _resolve_kw = {k: kwargs[k] for k in ("bold", "italic") if kwargs.get(k) is not None}
        _apply_point_size(lbl, float(pt) if pt is not None else _POINT_PT_BY_PIXEL.get(pixel_size, pixel_size), **_resolve_kw)
    except Exception:
        pass
    if kwargs.get("elide"):
        # W7: elide paints truncated text but does NOT shrink
        # QLabel.sizeHint (full-text hint forces the 296px column into
        # h-scroll; minimum_width alone only sets minimumSize). Ignored
        # lets the layout reserve the minimum instead of the hint.
        try:
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, lbl.sizePolicy().verticalPolicy())
        except Exception:
            pass
    return lbl
