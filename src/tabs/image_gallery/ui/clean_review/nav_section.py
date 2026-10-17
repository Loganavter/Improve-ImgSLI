"""Clean Review (S3) keyboard navigation — a **trap-only** modal section.

S3 has no bespoke keyboard navigation yet: full in-overlay navigation is a later
wave. What the overlay must do *now* is declare modality, so the toolkit
``NavigationManager`` (``sli_ui_toolkit/ui/managers/navigation_manager.py``)
treats the visible overlay as a modal ceiling:

* every arrow, Tab/Backtab and any ``extra_keys`` is routed into the overlay;
* a focus steal by a widget behind the veil is pulled back
  (``_reclaim_modal_focus``);
* the gallery grid behind the veil receives no key or focus.

The section itself is a trap: :meth:`CleanReviewNavSection.navigate` declines
every key (the manager then consumes the arrow at the modal edge), and
:attr:`CleanReviewNavSection.extra_keys` is deliberately empty, so ``Esc`` stays
native — the overlay's own ``keyPressEvent`` still closes it (``Esc`` is neither
an arrow nor claimed as an extra key, so the manager never intercepts it).

Register/unregister ride the overlay's show/close lifecycle
(``clean_review/__init__.py``: registration at the end of ``show_for`` after
``show_overlay()``; unregistration first thing in every close path — ``hide``,
``hideEvent``, ``closeEvent``). Both are idempotent and fail-open.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import NavigationManager
from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

#: Overlay attribute holding the registered section (idempotent register).
SECTION_ATTR = "_clean_review_nav_section"


class CleanReviewNavSection:
    """Modal-ceiling ``NavigationSection`` for the Clean Review overlay.

    Trap-only: it declares the overlay modal and claims the whole overlay
    subtree (``owns``), so the manager's ceiling never hands a key or the focus
    to a widget behind the veil. It navigates nothing — ``focus_first`` /
    ``focus_last`` simply land the cursor on the overlay itself (which is
    ``StrongFocus`` from ``TopLevelInWindowOverlay``), and ``navigate`` declines
    every key so the manager consumes an arrow at the modal edge.
    """

    def __init__(self, overlay: QWidget) -> None:
        self._overlay = overlay

    @property
    def modal(self) -> bool:
        """The overlay owns the keyboard for its window while it is visible.

        Read by the manager via ``getattr(spec, "modal", False)`` (the same raw
        read as ``extra_keys``) — must stay a property, never a method.
        """
        return True

    @property
    def extra_keys(self) -> frozenset:
        """Deliberately empty: ``Esc`` must stay native.

        Claiming anything here (notably ``Esc``) would route it through the
        section and could stop the overlay from closing by keyboard.
        """
        return frozenset()

    def owns(self, widget) -> bool:  # noqa: ANN001 (duck-typed section protocol)
        """The whole overlay subtree belongs to the section (trap, not rows)."""
        try:
            return bool(widget is self._overlay or self._overlay.isAncestorOf(widget))
        except Exception:
            return False

    def navigate(self, key: int, widget) -> bool:  # noqa: ANN001
        """Navigate nothing — full S3 keyboard navigation is a later wave."""
        return False

    def focus_first(self, ref_x=None, *, reason=None) -> bool:  # noqa: ANN001
        """Land the cursor on the overlay itself (nothing to enter yet)."""
        return self._focus_overlay(reason)

    def focus_last(self, ref_x=None, *, reason=None) -> bool:  # noqa: ANN001
        """Same as :meth:`focus_first` — the overlay is the only target."""
        return self._focus_overlay(reason)

    def _focus_overlay(self, reason) -> bool:
        try:
            self._overlay.setFocus(reason or focus_reason())
            return True
        except Exception:
            return False


def section_of(overlay):
    """The registered section, or ``None`` while the overlay is closed."""
    return getattr(overlay, SECTION_ATTR, None)


def register(overlay) -> None:
    """Make the overlay a modal navigation section while visible (idempotent)."""
    if overlay is None:
        return
    try:
        section = section_of(overlay)
        if section is None:
            section = CleanReviewNavSection(overlay)
            setattr(overlay, SECTION_ATTR, section)
        NavigationManager.get_instance().register(overlay, section)
    except Exception:
        return


def unregister(overlay) -> None:
    """Drop the section again (idempotent, fail-open)."""
    if overlay is None:
        return
    try:
        NavigationManager.get_instance().unregister(overlay)
    except Exception:
        pass
    try:
        setattr(overlay, SECTION_ATTR, None)
    except Exception:
        pass


__all__ = [
    "CleanReviewNavSection",
    "SECTION_ATTR",
    "register",
    "section_of",
    "unregister",
]
