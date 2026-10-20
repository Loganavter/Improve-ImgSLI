"""Ask AI flyout (A3) — the anchored shell around the shared ask surface.

``AskAiSurface`` (``ui/ask_surface.py``) is the body: question field, answer
pane, status badge and the Q/A history list. This class only adds the flyout
lifecycle — ``BaseFlyout`` positioning/fade, the manual resize grip, the saved
user size and the Enter fallback — so the tab-level sidebar can embed the SAME
surface instance without forking any ask logic.

Anchored to a card, a series header or a region selection. Advisory only: the
surface renders text, it never mutates rank/selection/store. All async work is
dispatched by the controller (``GalleryController.ask_ai_question``).

Audit-Meta: pattern=state-machine size=exempt reason="one flyout lifecycle: show/fade/reposition/resize state around the shared surface; splitting would scatter the shell lifecycle"
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import BaseFlyout

from tabs.image_gallery.ui import ask_nav
from tabs.image_gallery.ui.ask_ai_grip import AskAiResizeGrip
from tabs.image_gallery.ui.ask_surface import (
    HISTORY_LIMIT,
    HISTORY_ROW_HEIGHT,
    IMAGE_HREF_SCHEME,
    MIN_HEIGHT_PX,
    MIN_WIDTH_PX,
    AskAiSurface,
)

#: Status-badge suffix for a replayed cached answer. Shown verbatim (the
#: surface appends it to the badge); injected localized via ``set_texts``.
_CACHED_SUFFIX = " · cached"


class AskAiFlyout(BaseFlyout):
    """Free-form question + AI result, anchored to a card or series header."""

    flyout_group = "gallery_ask_ai"
    # Sequenced cycle: if another flyout is still fading out, wait for it to
    # finish before this one opens (FlyoutManager deferral) — no overlapping
    # fades.
    wait_for_close_before_show = True

    submitted = Signal(str)
    closed = Signal()
    #: An answer image link was clicked — carries the item's path. The host
    #: opens Quick Look for it.
    imageActivated = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._owner = parent
        self._surface: AskAiSurface | None = None
        self._surface_bound = False
        self._cached_suffix = _CACHED_SUFFIX
        self._grow_up = False
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)

        # User resize support (toolkit flyouts auto-size only).
        self._user_size: tuple[int, int] | None = None
        self._grip = AskAiResizeGrip(self)
        try:
            self.setMinimumSize(scaled_px(MIN_WIDTH_PX), self._min_height())
        except Exception:
            pass

    # -- shared surface -----------------------------------------------------

    def attach_surface(self, surface: AskAiSurface | None) -> AskAiSurface:
        """Install *surface* in the flyout shell (creating one when omitted)."""
        if surface is None:
            surface = AskAiSurface(self.container)
        changed = surface is not self._surface
        if changed:
            try:
                if self._surface is not None:
                    self.content_layout.removeWidget(self._surface)
            except Exception:
                pass
            # The docked panel may still hold the shared surface (and its
            # content-well reference); hand it over explicitly.
            try:
                owner = getattr(self, "_owner", None)
                sidebar = getattr(owner, "_ask_ai_sidebar", None)
                if sidebar is not None and getattr(sidebar, "_surface", None) is surface:
                    sidebar.detach_surface()
            except Exception:
                pass
            self._surface = surface
            self.content_layout.addWidget(surface)
            try:
                surface.setObjectName("gallery_ask_ai_surface")
            except Exception:
                pass
        try:
            owner = getattr(self, "_owner", None)
            if owner is not None:
                owner._ask_ai_surface = surface  # type: ignore[attr-defined]
        except Exception:
            pass
        self._bind_surface()
        self._sync_aliases()
        try:
            surface.show()
        except Exception:
            pass
        return surface

    def detach_surface(self) -> AskAiSurface | None:
        """Hand the surface back to the owner (the sidebar is taking it)."""
        surface = self._surface
        if surface is None:
            return None
        try:
            self.content_layout.removeWidget(surface)
        except Exception:
            pass
        try:
            owner = getattr(self, "_owner", None)
            surface.setParent(owner)
            surface.hide()
        except Exception:
            pass
        self._surface = None
        return surface

    def surface(self) -> AskAiSurface | None:
        """The shared ask surface currently hosted (``None`` before first use)."""
        return self._surface

    def _ensure_surface(self) -> AskAiSurface:
        surface = self._surface
        if surface is None:
            # A standalone flyout (tests/toolkit preview) gets its own surface;
            # the gallery use-case installs the shared instance explicitly via
            # ``attach_surface`` so two flyouts can never adopt each other's.
            surface = self.attach_surface(None)
        return surface

    def _bind_surface(self) -> None:
        surface = self._surface
        if surface is None or self._surface_bound:
            return
        try:
            surface.submitted.connect(self._emit_submitted)
            surface.imageActivated.connect(self.imageActivated.emit)
            surface.layoutRequested.connect(self._relayout)
        except Exception:
            pass
        self._surface_bound = True

    def _emit_submitted(self, question: str) -> None:
        try:
            self.submitted.emit(question)
        except Exception:
            pass

    def _sync_aliases(self) -> None:
        """Expose the surface's rows under the shell's historical attribute names.

        Tests and older call sites read ``flyout._edit`` / ``_result`` /
        ``_status`` / ``_history``; keeping the aliases avoids a second
        surface API just for the flyout host.
        """
        surface = self._surface
        if surface is None:
            return
        for name in (
            "_edit",
            "_title",
            "_scope",
            "_images_toggle",
            "_result",
            "_status",
            "_history",
            "_history_title",
            "_history_list",
            "_history_empty",
        ):
            try:
                setattr(self, name, getattr(surface, name))
            except Exception:
                pass

    # -- delegation (same API the gallery used before the split) ------------

    def set_texts(
        self,
        *,
        title: str | None = None,
        busy: str | None = None,
        read_badge: str | None = None,
        error: str | None = None,
        images_hint: str | None = None,
        images_downsample: str | None = None,
        model: str | None = None,
        cached: str | None = None,
        history: str | None = None,
        history_title: str | None = None,
        history_empty: str | None = None,
    ) -> None:
        """Inject localized chrome strings (from the tab i18n)."""
        if cached is not None:
            self._cached_suffix = str(cached)
        self._ensure_surface().set_texts(
            title=title,
            busy=busy,
            read_badge=read_badge,
            error=error,
            images_hint=images_hint,
            images_downsample=images_downsample,
            model=model,
            cached=cached,
            history=history,
            history_title=history_title,
            history_empty=history_empty,
        )

    def set_images_tooltip(self, text: str) -> None:
        """Tooltip of the include-images toggle (two lines: meaning + downscale)."""
        self._ensure_surface().set_images_tooltip(text)

    def include_images(self) -> bool:
        """Whether the question should carry the images (VLM) or metrics only."""
        return self._ensure_surface().include_images()

    def _on_images_toggled(self) -> None:
        self._ensure_surface()._on_images_toggled()

    def _on_field_submitted(self, question: str) -> None:
        self._ensure_surface()._on_field_submitted(question)

    def _emit_submit(self) -> None:
        self._ensure_surface().emit_submit()

    def set_busy(self, busy: bool) -> None:
        self._ensure_surface().set_busy(bool(busy))
        self._relayout()

    def set_history_count(self, count: int) -> None:
        """Show ``"N previous questions"`` for the persisted Q/A log (0 hides)."""
        self._ensure_surface().set_history_count(count)
        self._relayout()

    def set_history_records(self, records, *, show_tail: bool = False) -> None:  # type: ignore[no-untyped-def]
        """Render the stored Q/A exchanges (oldest → newest)."""
        self._ensure_surface().set_history_records(records, show_tail=show_tail)
        self._relayout()

    def show_result(
        self,
        text: str,
        *,
        model: str = "",
        backend: str = "",
        cached: bool = False,
        links: dict | None = None,
    ) -> None:
        self._ensure_surface().show_result(
            text, model=model, backend=backend, cached=cached, links=links
        )

    def show_error(self, message: str) -> None:
        self._ensure_surface().show_error(message)

    def has_answer(self) -> bool:
        return self._ensure_surface().has_answer()

    # -- open / show --------------------------------------------------------

    def open_for(
        self,
        anchor: QWidget,
        *,
        scope_label: str = "",
        default_prompt: str = "What matters here?",
        title: str = "",
        initial_result=None,  # type: ignore[no-untyped-def]
        initial_error: str = "",
        initial_links: dict | None = None,
        grow_up: bool = False,
        show_images_toggle: bool = True,
        history_count: int | None = None,
        history_records: list | None = None,
    ) -> None:
        """Reset + show under *anchor*; focus lands in the question field."""
        surface = self._ensure_surface()
        surface.prepare_scope(
            scope_label=scope_label,
            default_prompt=default_prompt,
            title=title,
            initial_result=initial_result,
            initial_error=initial_error,
            initial_links=initial_links,
            show_images_toggle=show_images_toggle,
            history_count=history_count,
            history_records=history_records,
        )
        surface.set_title_visible(True)
        # Track the live content floor (the history/title rows collapse when
        # empty) — construction ran before any surface existed, so re-pin it.
        saved_size = getattr(self, "_user_size", None)
        if saved_size is None:
            try:
                self.setMinimumSize(scaled_px(MIN_WIDTH_PX), self._min_height())
            except Exception:
                pass
        # A remembered manual size must land on the FIRST frame: pin the
        # flyout's minimum to it so show_aligned()'s adjustSize() cannot
        # collapse it to the min-content size for the fade-in and then jump
        # once _relayout applies the saved size after the animation.
        if saved_size is not None:
            try:
                self.setMinimumSize(int(saved_size[0]), int(saved_size[1]))
            except Exception:
                pass
        try:
            # ``grow_up`` pins the flyout's BOTTOM-CENTER to the anchor's
            # TOP-CENTER so a taller wrapped result expands upward (the
            # region-inspection flyout above the held selection); the default
            # grows downward from the anchor's bottom-left.
            anchor_point = "top-center" if grow_up else "bottom-left"
            flyout_point = "bottom-center" if grow_up else "top-left"
            self._grow_up = bool(grow_up)
            self.show_aligned(
                anchor,
                anchor_point=anchor_point,
                flyout_point=flyout_point,
                offset=scaled_px(8),
                animation="fade",
            )
        except Exception:
            try:
                self.show_aligned(anchor)
            except Exception:
                pass
        # Register the surface's rows as a navigation section while visible.
        ask_nav.register(self, surface)
        self._relayout()

    def reshow(self, anchor: QWidget) -> None:
        """Re-show in place WITHOUT resetting the question/result pane.

        Used when a late answer arrives after the user dismissed the flyout —
        the answer must not vanish silently.
        """
        if anchor is None:
            return
        try:
            grow_up = bool(getattr(self, "_grow_up", False))
            self.show_aligned(
                anchor,
                anchor_point="top-center" if grow_up else "bottom-left",
                flyout_point="bottom-center" if grow_up else "top-left",
                offset=scaled_px(8),
                animation="none",
                grab_focus=False,
            )
        except Exception:
            try:
                self.show_aligned(anchor, grab_focus=False)
            except Exception:
                pass
        surface = self._surface
        if surface is not None:
            ask_nav.register(self, surface)

    def restore_focus_on_hide(self) -> bool:
        return False

    # -- shell layout -------------------------------------------------------

    def _relayout(self) -> None:
        """Re-run the shell layout after the wrapped answer changed.

        A wrapped ``Label`` only reports its tall height once the parent width
        is fixed; without this the result overflows its row and overlaps the
        status line. ``reposition()`` is the toolkit's sanctioned re-size path
        (a raw ``adjustSize()`` collapses the surface because the container is
        briefly hidden for the fade).
        """
        try:
            surface = self._surface
            if surface is not None:
                surface.updateGeometry()
            if not self.isVisible():
                return
            # Never resize while the show animation is running: clearing the
            # fade snapshot mid-animation paints the panel white until the
            # animation ends. Defer the resize to the animation's finish.
            anim = getattr(self, "_show_animation", None)
            if anim is not None:
                if not getattr(self, "_ask_reposition_pending", False):
                    self._ask_reposition_pending = True
                    try:
                        anim.finished.connect(self._after_show_reposition)
                    except Exception:
                        self._ask_reposition_pending = False
                return
            if getattr(self, "_user_size", None) is not None:
                # Manual size wins over auto-size: re-wrap at the user's width
                # and grow only if the content needs more height.
                self.apply_user_size(*self._user_size)
                return
            self._reposition_now()
        except Exception:
            pass

    def _after_show_reposition(self) -> None:
        self._ask_reposition_pending = False
        if not self.isVisible():
            return
        if getattr(self, "_user_size", None) is not None:
            self.apply_user_size(*self._user_size)
        else:
            self._reposition_now()

    def _reposition_now(self) -> None:
        # Do not yank focus back to the field if the user is already typing a
        # follow-up when the previous answer lands.
        prev = getattr(self, "_skip_focus_grab", False)
        self._skip_focus_grab = True
        try:
            self.reposition()
        finally:
            self._skip_focus_grab = prev

    def _min_height(self) -> int:
        """Minimum shell height the content layout actually needs (+ shadow)."""
        m = self.SHADOW_RADIUS
        try:
            layout = self.container.layout()
            if layout is not None:
                layout.activate()
                need = int(layout.minimumSize().height()) + 2 * m
                if need > 2 * m:
                    return need
        except Exception:
            pass
        return scaled_px(MIN_HEIGHT_PX)

    # -- manual resize ------------------------------------------------------

    def apply_user_size(self, width: int, height: int) -> None:
        """Set the flyout to a user-chosen size (grip drag), keeping content."""
        m = self.SHADOW_RADIUS
        w = max(scaled_px(MIN_WIDTH_PX), int(width))
        h = max(self._min_height(), int(height))
        try:
            self.resize(w, h)
            self.container.setGeometry(m, m, w - 2 * m, h - 2 * m)
            layout = self.container.layout()
            if layout is not None:
                layout.activate()
                # Grow (never shrink below the user's height) if the wrapped
                # content needs more room.
                try:
                    need = int(layout.heightForWidth(w - 2 * m)) + 2 * m
                except Exception:
                    need = 0
                if need > h:
                    h = need
                    self.resize(w, h)
                    self.container.setGeometry(m, m, w - 2 * m, h - 2 * m)
                    layout.activate()
        except Exception:
            pass
        self._user_size = (w, h)
        self._layout_grip()

    def _layout_grip(self) -> None:
        try:
            grip = self._grip
            grip.move(self.width() - grip.width() - 3, self.height() - grip.height() - 3)
            grip.raise_()
        except Exception:
            pass

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        self._layout_grip()

    # -- keys / lifecycle ---------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        # The flyout's own key handler is the reliable Enter path: the toolkit
        # nav section does not always deliver Return to the focused field in
        # the live window. Return always sends.
        try:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._emit_submit()
                event.accept()
                return
        except Exception:
            pass
        super().keyPressEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().hideEvent(event)
        # BaseFlyout hides itself while its own __init__ is still running, so
        # every shell attribute must be read tolerantly here.
        surface = getattr(self, "_surface", None)
        if surface is not None:
            surface.persist_draft()
        ask_nav.unregister(self)
        try:
            self.closed.emit()
        except Exception:
            pass


__all__ = [
    "AskAiFlyout",
    "AskAiSurface",
    "HISTORY_LIMIT",
    "HISTORY_ROW_HEIGHT",
    "IMAGE_HREF_SCHEME",
    "MIN_HEIGHT_PX",
    "MIN_WIDTH_PX",
]
