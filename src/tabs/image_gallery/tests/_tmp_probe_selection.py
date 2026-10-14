def test_probe_selection_accent(qapp):
    from core.theme import DARK_THEME_PALETTE, LIGHT_THEME_PALETTE
    from sli_ui_toolkit.managers import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)
    tm.set_theme("dark", qapp, await_ripples=False)
    try:
        tm._flush_pending_theme()
    except Exception:
        pass
    qapp.processEvents()

    from ui.theming import try_resolve_theme_color
    from ui.widgets.shelf.selection import selection_accent_color

    for tok in ("accent", "Base", "Window", "surface.background"):
        c = try_resolve_theme_color(tm, tok)
        print("PROBE token", tok, "=", c.name() if hasattr(c, "name") else c)
    print("PROBE dark selection_accent() =", selection_accent_color().name())
    print("PROBE dark selection_accent(tm) =", selection_accent_color(tm).name())
    import ui.widgets.shelf.selection as _sel

    m = _sel._theme_manager_or_none(None)
    print("PROBE _theme_manager_or_none(None) =", type(m).__name__ if m is not None else None, "same=", m is tm)
    print("PROBE _raw_accent() =", _sel._raw_accent().name())
    try:
        from sli_ui_toolkit.ui.theme_manager import ThemeManager as _TM2

        print("PROBE ui.theme_manager import OK, same instance =", _TM2.get_instance() is tm)
    except Exception as e:
        print("PROBE ui.theme_manager import FAILED:", type(e).__name__, e)

    tm.set_theme("light", qapp, await_ripples=False)
    try:
        tm._flush_pending_theme()
    except Exception:
        pass
    qapp.processEvents()
    print("PROBE light selection_accent =", selection_accent_color().name())
