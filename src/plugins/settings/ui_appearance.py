"""The one appearance-apply path: scale + theme + font in one frozen batch.

``SettingsApplicationService`` used to enforce the apply order with a comment
(``Order matters (trap §2.7.1)``) in three different code paths — the QSS push
that resets WA_SetFont pins, the app-font re-cascade that fires no
``ApplicationFontChange`` for an identical font, and the guaranteed
``font_changed`` that must come after both. Order held by prose is the disease
``plan-theme-refresh-systemic`` closed with owned order on the theme side; this
module is the metrics/appearance analogue.

:func:`apply_appearance` is the single entry point: callers say **which axes**
changed, this path owns **the order** (scale → theme → font), one paint freeze
(:meth:`ThemeManager.suspend_widget_updates`), one deferred-resync flush and one
appearance-bus batch (:meth:`UiMetrics.begin_appearance` /
:meth:`UiMetrics.end_appearance`), so the bus emits once with the union of the
axes that changed instead of once per producer.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication

from shared_toolkit.ui.managers.font_manager import FontManager
from ui.theming import reapply_application_theme


def _flush_deferred_scale_resyncs(app) -> None:
    """Run the singleShot(0)-deferred scale resyncs synchronously.

    Called while top-level paints are frozen (see :func:`apply_appearance`), so
    the first painted frame after the scale change is already the final layout —
    nothing needs a later event-loop tick to settle.
    """
    if app is None:
        return
    for top in app.topLevelWidgets():  # ALLOWED: system-wide scale fan-out — applies UiScale to every top-level window generically, not tab-specific
        try:
            bar = getattr(top, "_custom_title_bar", None) or getattr(
                top, "_csd_title_bar", None
            )
            sync = getattr(bar, "_sync_balance_spacer", None)
            if callable(sync):
                sync()
        except Exception:
            pass
        try:
            ui = getattr(top, "ui", None)
            strip = getattr(ui, "workspace_tabs", None) if ui is not None else None
            finish = getattr(strip, "_finish_scale_resync", None)
            if callable(finish):
                finish()
        except Exception:
            pass


def _apply_theme_axis(theme_manager, theme: str, window, app) -> None:
    """Push *theme* through the owner that resolves it.

    The main window owns the ``auto``/``system`` → concrete-palette mapping
    (``Window.apply_application_theme``); without one, the toolkit manager is
    the fallback (it normalizes ``dark``/``light`` itself).
    """
    apply_to_window = getattr(window, "apply_application_theme", None)
    if callable(apply_to_window):
        apply_to_window(theme)
        return
    theme_manager.set_theme(theme, app)


def apply_appearance(
    store,
    *,
    scale=None,
    theme: str | None = None,
    font: bool = False,
    window=None,
    app=None,
) -> frozenset[str]:
    """THE appearance-apply path: scale, theme and font in one frozen batch.

    Order — **scale → theme → font**, owned here and never by a comment at a
    call site (this replaces the ``Order matters (trap §2.7.1)`` prose):

    * ``UiScale.set_factor`` first: its ``scale_changed`` fan-out re-scales the
      Npx literals in the host QSS;
    * then the theme / QSS push — the requested ``theme`` when given, otherwise
      the factor's QSS re-push (``reapply_application_theme``);
    * the UI font is re-applied **last**: the QSS push resets WA_SetFont
      pins without firing ``ApplicationFontChange`` and the application font
      itself does not change with the factor, so the guaranteed
      ``font_changed`` must come after both or every ``Label`` /
      ``UiFont.apply()`` pin / HUD label stays on the reset default size.

    Paints are frozen across the whole chain (``suspend_widget_updates``) and the
    ``singleShot(0)``-deferred scale resyncs are flushed while still frozen, so
    the first painted frame is already final and the UI does not "transform in
    steps".

    The chain runs inside one ``UiMetrics.begin_appearance()`` /
    ``end_appearance()`` batch, so the appearance bus emits **once**, carrying
    the union of the axes that changed: the producers report ``{"scale"}`` /
    ``{"theme"}`` / ``{"font"}`` in between and this path declares the axes it
    observed change — a producer no-op cannot silently drop an axis the caller
    asked for. A theme apply deferred by an active button ripple
    (``await_ripples``) is the one exception: it lands after the batch on its
    own emission, exactly as it did before this path existed.

    ``scale`` (new factor) / ``theme`` (new theme name) are ``None`` to leave
    that axis alone; ``font=True`` re-applies the UI font from *store*.
    ``window`` is optional and only used for the theme axis. Returns the axes
    this call changed.
    """
    from sli_ui_toolkit.managers import UiFont, UiScale, ThemeManager
    from sli_ui_toolkit.ui.managers import UiMetrics

    if scale is None and theme is None and not font:
        return frozenset()

    logger = logging.getLogger("ImproveImgSLI")
    metrics = UiMetrics.get_instance()
    theme_manager = ThemeManager.get_instance()
    ui_scale = UiScale.get_instance()
    ui_font = UiFont.get_instance()
    app = app if app is not None else QApplication.instance()

    changed: set[str] = set()
    metrics.begin_appearance()
    try:
        with theme_manager.suspend_widget_updates(app):
            if scale is not None:
                factor_before = ui_scale.factor()
                ui_scale.set_factor(float(scale))
                if ui_scale.factor() != factor_before:
                    changed.add("scale")
            if theme is not None:
                theme_before = theme_manager.get_current_theme()
                _apply_theme_axis(theme_manager, theme, window, app)
                if theme_manager.get_current_theme() != theme_before:
                    changed.add("theme")
            elif scale is not None and app is not None:
                # No theme requested: still re-push the theme QSS so its Npx
                # literals follow the new factor in the same frozen pass.
                try:
                    reapply_application_theme(app)
                except Exception:
                    logger.warning(
                        "reapply_application_theme failed during appearance apply",
                        exc_info=True,
                    )
            if font:
                try:
                    FontManager.get_instance().apply_from_state(store)
                except Exception:
                    logger.warning(
                        "font re-apply failed during appearance apply",
                        exc_info=True,
                    )
                # Belt-and-braces after the QSS push (FontManager already syncs):
                # the pinned-font resync must be the last word on the frame.
                ui_font.sync_from_application()
                changed.add("font")
            if scale is not None:
                _flush_deferred_scale_resyncs(app)
        if changed:
            metrics.emit_appearance(changed)
    finally:
        metrics.end_appearance()
    return frozenset(changed)
