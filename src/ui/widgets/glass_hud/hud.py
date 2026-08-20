from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import time

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

from shared.rendering.glass_panel import GlassPanelSpec
from ui.theming import resolve_theme_color
from ui.widgets.flyout_debug import flyout_debug, flyout_debug_enabled
from ui.widgets.glass_hud import target_watch
from ui.widgets.glass_hud.panel_display import create_glass_panel_display_widget

_BLUR_RADIUS_PX = 16.0


def _child_debug_info(container: QWidget) -> list:
    """Per-child geometry + font snapshot for `_reflow_container()`'s trace
    -- font family/pointSize/pixelSize/key are included (not just size/
    sizeHint) because a sizeHint jump with unchanged text can only be a
    font-metrics change (family, point/pixel size, or hinting), and
    size/sizeHint alone can't distinguish that from a plain text-length
    change. See the "grew after clicking OK with nothing touched" report
    in docs/dev/rendering/glass-panel-text-vibrancy-plan.md Phase 3."""
    info = []
    for c in container.findChildren(QWidget):
        font = c.font()
        text = c.text() if hasattr(c, "text") else None
        info.append(
            (
                c.__class__.__name__,
                c.size(),
                c.sizeHint(),
                font.family(),
                font.pointSizeF(),
                font.pixelSize(),
                font.key(),
                text,
            )
        )
    return info


def caller_str(depth: int = 6) -> str:
    """Short `file:line in func` chain for the last few frames outside this
    module -- who actually triggered this `_position()`/`_reflow_container()`
    call. Cheap enough only because it's gated behind
    `flyout_debug_enabled()` by every caller."""
    import traceback

    frames = traceback.extract_stack()[:-1]
    frames = [f for f in frames if "glass_hud/hud.py" not in f.filename][-depth:]
    return " <- ".join(f"{f.filename.split('/')[-1]}:{f.lineno}:{f.name}" for f in frames)


class GlassHUD(BaseFlyout):
    """Pinned flyout with a frosted-glass backdrop.

    Shared base for the corner HUD chips (``InfoHUD``, ``ZoomIndicator``):
    both are persistent, always-on-top overlays inset into a canvas corner
    rather than dismissible popups (see ``pinned=True`` and
    ``ui/flyout_policy.py``), and both want the same glassmorphism look.

    Split across two pieces:
    - ``shared.rendering.glass_panel.GlassPanelRenderer`` (canvas-owned)
      computes the actual blur/tint/border/rounded-crop sprite every frame,
      reading the target canvas's own ``colorTexture()`` -- which the canvas
      never draws any glass panel *into*, on purpose (see that module's
      docstring): a panel that read back its own previously-drawn output as
      part of computing its own next backdrop converged to "blurred view of
      itself" within a couple of frames, independent of the real content
      behind it -- confirmed live at zoom levels from 100% to >1000%.
    - ``self._display`` (a small ``GlassPanelDisplayWidget``, one per
      instance) just blits that ready-made sprite onto the screen -- no
      blur/tint/crop/coordinate math of its own at all. This widget (the
      flyout itself) is fully transparent (``WA_TranslucentBackground``,
      ``paintEvent`` a no-op) and only hosts real content (buttons, labels)
      on top of ``self._display``.

    Subclasses must set ``self._target_widget`` (the canvas the panel is
    drawn onto) before calling `_refresh_backdrop()`, and are responsible
    for their own positioning (`_position()` / `reposition()` /
    `sync_position()`) -- this base only owns the backdrop registration and
    the display widget.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent, pinned=True)
        # Both current subclasses (InfoHUD, ZoomIndicator) are purely
        # informational corner chips -- read-only labels plus, at most, a
        # NoFocus reset button -- with nothing for keyboard navigation to
        # reach. Skip BaseFlyout.show()'s focus grab and NavigationSection
        # registration here, once, rather than requiring every subclass to
        # remember it: without this, a resync while already visible steals
        # keyboard focus from whatever the user was actually doing.
        self._skip_focus_grab = True
        # BaseFlyout.__init__ (create_shadow_surface) reserves an 8px
        # SHADOW_RADIUS margin around `container` on every side by default,
        # meant for the CPU drop-shadow gradient other (non-GPU) flyouts
        # paint into via paint_shadowed_surface. GlassHUD's paintEvent is a
        # deliberate no-op (see below) -- it never paints that margin -- so
        # left at its default it's just blank, unpainted widget space
        # showing the *raw* backdrop straight through: no blur, no tint, and
        # square-cornered where the actual glass panel is rounded. That
        # reads as a visible "backing plate" around the rounded glass shape,
        # not a shadow. Zero it out: this widget's own bounding rect should
        # equal `container`'s, with nothing left over to paint or leak
        # through. (`_position()`/`adjustSize()` in InfoHUD/ZoomIndicator
        # don't hardcode SHADOW_RADIUS anywhere, so this is safe to change
        # without touching their placement math.)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._target_widget: QWidget | None = None
        # IMGSLI_FLYOUT_DEBUG=1 only: call-rate reporting in
        # _refresh_backdrop() / _position(), see there.
        self._debug_frame_count = 0
        self._debug_frame_window_start = time.monotonic()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # container has a QGraphicsEffect (RoundedClipEffect) attached, and
        # Qt captures effect sources into an offscreen pixmap that defaults
        # to opaque (the widget's palette window color) unless the widget
        # itself is marked translucent. Without this, container's own empty
        # space (around its content_layout labels) would capture as an
        # opaque rounded box, hiding the canvas-drawn glass panel underneath.
        self.container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Blits the ready-made sprite (computed canvas-side) -- see class
        # docstring. A sibling of container (not a descendant), stacked
        # below it so container's real content (labels, buttons) paints on
        # top; sized to match container exactly, same as the old
        # cross-widget backdrop widget this replaces. Plain-QWidget by
        # default (see ui/widgets/glass_hud/panel_display.py's
        # GlassPanelDisplayWidget docstring for why).
        self._display = create_glass_panel_display_widget(self)
        self._display.stackUnder(self.container)
        self._display.setGeometry(self.container.geometry())

        self.theme_manager.theme_changed.connect(self._apply_glass_style)
        self._apply_glass_style()

    def paintEvent(self, event):
        """No-op: the target canvas draws the entire shell (fill, border) --
        see class docstring. Deliberately does *not* call
        `super().paintEvent()`, which would paint BaseFlyout's CPU
        background/border/shadow on top of the canvas-drawn panel showing
        through this widget's transparent background."""

    def _reflow_container(self) -> None:
        """Recomputes `self.container`'s layout tree bottom-up so its size
        reflects the *current* content -- call before reading
        `self.container.size()` / any child's `size()` (e.g. from
        `_position()`, before `adjustSize()`/`setGeometry()`).

        A single `self.container.layout().invalidate()` +
        `.activate()` is NOT enough when content lives inside a *nested*
        layout (e.g. `ZoomIndicator`'s `row`, a plain `QWidget` with its own
        `QHBoxLayout` holding the label + reset button, added to
        `content_layout` as one item): `container.layout().activate()`
        only asks its own direct children (here, `row`) for their current
        `sizeHint()` -- if `row`'s *own* layout was never itself
        invalidated, that sizeHint() answers from a stale cache pinned to
        whatever `row` needed the last time ITS layout was activated, not
        the wider size a longer label text now needs. Confirmed live and
        reproduced in isolation (`QLayout.invalidate()` on the nested
        layout alone is insufficient too -- needs `.activate()` on it as
        well, not just a dirty flag): calling `label.setText()` to a much
        longer string, then only invalidating+activating the *outer*
        layout, left the container permanently stuck at the old, narrower
        width -- text overflowing past the panel's own rounded edge,
        reported live as "надпись не влезает целиком в пространство"
        (the label doesn't fit) on `ZoomIndicator` with the Russian
        "Приближение: NNN%" (longer than English "Zoom: NNN%", so more
        likely to actually need the container to grow past whatever width
        it last settled on). A full language switch happened to fix it by
        accident -- `QEvent::LanguageChange` makes Qt invalidate geometry
        across the whole widget tree itself, which is what this method
        does deliberately and only for this one flyout's own subtree.
        """
        if flyout_debug_enabled():
            flyout_debug(
                "%s: _reflow_container() BEFORE container=%r children=%s caller=%s",
                type(self).__name__,
                self.container.size(),
                _child_debug_info(self.container),
                caller_str(),
            )
        for child in self.container.findChildren(QWidget):
            child_layout = child.layout()
            if child_layout is not None:
                child_layout.invalidate()
                child_layout.activate()
        if self.container.layout():
            self.container.layout().invalidate()
            self.container.layout().activate()
        if flyout_debug_enabled():
            flyout_debug(
                "%s: _reflow_container() AFTER container=%r children=%s",
                type(self).__name__,
                self.container.size(),
                _child_debug_info(self.container),
            )

    def _debug_frame_submitted(self) -> None:
        """See ``glass_hud.target_watch.debug_frame_submitted`` --
        kept as a same-named instance method since ``_watch_target()``
        connects ``self._debug_frame_submitted`` as a Qt signal slot."""
        target_watch.debug_frame_submitted(self)

    def _connect_zoom_refresh(self, target_widget: QWidget) -> None:
        """See ``glass_hud.target_watch.connect_zoom_refresh``."""
        target_watch.connect_zoom_refresh(self, target_widget)

    def _watch_target(self, target_widget: QWidget | None) -> None:
        """See ``glass_hud.target_watch.watch_target``. Must be
        called *before* the caller assigns ``self._target_widget =
        target_widget`` -- it reads the current value as the *previous*
        target to disconnect from."""
        target_watch.watch_target(self, target_widget)

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._target_widget and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            self._resync()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # container's own geometry is already up to date here -- Qt runs
        # the layout pass synchronously as part of the resize.
        self._display.setGeometry(self.container.geometry())
        self._refresh_backdrop()

    def hideEvent(self, event):
        super().hideEvent(event)
        # BaseFlyout.__init__ calls QWidget.hide(self) before this
        # subclass's own __init__ body runs (so `pinned` flyouts start
        # hidden) -- _target_widget doesn't exist yet at that point.
        registry = getattr(getattr(self, "_target_widget", None), "glass_panels", None)
        if registry is not None:
            registry.unregister(id(self))

    def _resync(self) -> None:
        if self._target_widget is None or not self.isVisible():
            return
        self._position()
        self._raise_self()

    def _raise_self(self) -> None:
        """Raise above the canvas without stealing z-order from whatever
        ordinary flyout (font settings, unified lists, ...) is currently
        active.

        This HUD used to live in its own topmost ``LayerStack`` layer (see
        ``ui/flyout_policy.py`` git history), which incidentally also fixed
        this — at the cost of painting above context menus too. Now that it
        shares the base layer with everything else, a raw ``raise_()`` here
        (fired on every anchor resize/move, e.g. while the font-settings
        panel is open and being interacted with) would otherwise pop this
        HUD above that panel. Re-raising the active flyout right after
        keeps it on top again.
        """
        self.raise_()
        from sli_ui_toolkit.managers import FlyoutManager

        manager = FlyoutManager.get_instance()
        active = getattr(manager, "_active_flyout", None)
        if active is None or active is self:
            return
        try:
            if active.isVisible():
                active.raise_()
        except RuntimeError:
            pass

    def restore_focus_on_hide(self) -> bool:
        """Don't steal window focus on hide (see BaseFlyout.hide()).

        Unlike a real dismiss, these HUDs hide constantly as routine state
        churn — ``ZoomIndicator`` on every zoom/pan tick back to its default,
        ``InfoHUD`` whenever a slot loses its image. The base
        ``activateWindow()``/``setFocus()`` on each of those was observed
        generating enough WindowDeactivate/Activate churn that *other*,
        non-pinned flyouts (font settings, unified lists, ...) read it as an
        outside-dismiss signal via ``FlyoutManager._dismiss_passive()`` and
        closed themselves prematurely. Context menus opt out of this same
        side effect for the same reason (see
        ``sli_ui_toolkit.ui.widgets.composite.context_menu.menu.ContextMenu``).
        """
        return False

    def _glass_tint(self) -> QColor:
        """Mixed into the blurred fill (``mix(blurred, tint.rgb, tint.a)`` in
        ``shared/rendering/shaders/glass_panel/glass_composite.frag``) --
        alpha is high enough that the tint dominates over whatever the live
        canvas actually shows, giving text drawn on top a predictable,
        mostly-canvas-independent background to contrast against. This is
        deliberately closer to Apple's "Regular" Liquid Glass variant
        (opaque-ish, adaptive tint) than "Clear" (near-transparent) -- the
        HIG notes Clear "needs a dimming layer for legibility" on its own.

        Legibility for the HUD's own labels (which paint their glyphs
        themselves in their normal theme color, on top of this glass) comes
        from this strong tint: the fill is close to the theme's flyout
        background regardless of what the canvas shows underneath, so the
        theme's own text color always contrasts against it. A separate
        backing chip (near-opaque rounded rect behind the text) was tried
        and dropped -- it either read as "the whole panel went solid" or,
        once thinned out, as a hard-edged sticker that never blended into
        the surrounding blur convincingly; and dynamic per-pixel text
        recoloring was tried and removed for reading as "liquid"/fluid (see
        improve-imgsli-internal-docs/docs/legacy/rendering/
        glass-panel-soft-threshold-adaptive-tint-plan.md)."""
        base = resolve_theme_color(self.theme_manager, "flyout.background")
        tint = QColor(base)
        tint.setAlpha(70 if self.theme_manager.is_dark() else 80)
        return tint

    def _border_highlight_color(self) -> QColor:
        """A crisp, always-visible contrasting border -- not a soft tinted
        edge. Apple's Liquid Glass HIG calls for elements to be
        "predominantly black or white and highlighted with a contrasting
        border" (see WWDC25 "Meet Liquid Glass" / the updated HIG). The
        glass fill's own brightness varies with whatever canvas content is
        behind it, but the *tint* mixed into that fill (`_glass_tint`,
        `flyout.background`) is fixed per theme -- so pick the opposite
        extreme from it (near-white on the dark-theme tint, near-black on
        the light-theme tint) at high alpha, guaranteeing contrast against
        the panel's own fill regardless of the live backdrop underneath."""
        return (
            QColor(255, 255, 255, 235)
            if self.theme_manager.is_dark()
            else QColor(0, 0, 0, 210)
        )

    def _apply_glass_style(self) -> None:
        """Just nudges a re-registration -- the actual tint/border/corner
        values are read fresh from `_glass_tint()`/`_border_highlight_color()`
        by `_refresh_backdrop()` every time it runs."""
        self._refresh_backdrop()

    def _refresh_backdrop(self) -> None:
        """(Re)registers this HUD's current screen rect + style with the
        target canvas's ``GlassPanelRegistry`` (see
        ``shared.rendering.glass_panel``) -- the canvas's own render pass
        picks this up on its next frame. A no-op if there's no target yet or
        the target doesn't expose a canvas-side registry (e.g. plain
        widgets used in tests)."""
        target = self._target_widget
        registry = getattr(target, "glass_panels", None)
        if target is None or registry is None or not self.isVisible():
            return
        top_left = target.mapFromGlobal(self.container.mapToGlobal(QPoint(0, 0)))
        rect_logical = QRect(top_left, self.container.size())
        dpr = self.devicePixelRatioF()

        registry.register(
            id(self),
            GlassPanelSpec(
                rect_logical=rect_logical,
                dpr=dpr,
                corner_radius_px=self.CONTENT_RADIUS * dpr,
                # 2px, not 1px: see glass_composite.frag's comment -- the
                # border band's feather (aaBorder=1.0/aaBorderInner=0.5)
                # needs borderWidthPx >= ~1.5-2.0 to keep a real (not
                # aliased, not zero-width-at-bad-phase) solid plateau given
                # single-sample-per-fragment rasterization.
                border_width_px=2.0 * dpr,
                border_color=self._border_highlight_color(),
                tint=self._glass_tint(),
                blur_radius_px=_BLUR_RADIUS_PX,
            ),
        )
        flyout_debug(
            "%s: _refresh_backdrop() key=%#x class=%s rect=%r dpr=%.2f",
            getattr(type(self), "flyout_group", "?"),
            id(self),
            type(self).__name__,
            rect_logical,
            dpr,
        )

GlassHUD.inspect_spec = InspectSpec(
    family="GlassHUD",
    state=(
        SpecField("target", "_target_widget", private=True),
        SpecField("pinned", "pinned"),
    ),
    docs="docs/dev/widgets/glass_hud.md",
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
GlassHUD.widget_descriptor = WidgetDescriptor(
    family=GlassHUD.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(GlassHUD.inspect_spec, 'config', ()),
        state=GlassHUD.inspect_spec.state,
        token_family=getattr(GlassHUD.inspect_spec, 'token_family', ()),
        regions=getattr(GlassHUD.inspect_spec, 'regions', False),
        layers=getattr(GlassHUD.inspect_spec, 'layers', False),
        docs=getattr(GlassHUD.inspect_spec, 'docs', ''),
        preview_seed=getattr(GlassHUD.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(GlassHUD.inspect_spec, 'apply_config_refresh', None),
    ),
)