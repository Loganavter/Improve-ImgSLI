"""Keyboard navigation for the colour picker's recents shelf as a 2D grid.

The shelf wraps its chips onto as many visual rows as the dialog width allows
(``RecentColorsRow._relayout_chips``), but the picker declares the whole shelf
as ONE ``ToolbarRowsSection`` row. That model walks Left/Right across
the chips in x order, so with two or more visual rows an arrow jumps between
rows instead of stepping to the neighbouring chip, and Up/Down leaves
the block although there is a row of chips above/below (owner report
2026-10-19, screenshot).

``RecentsGridNavSection`` models the real 2D grid, mirroring the gallery's
``GalleryGridNavSection`` (``tabs/image_gallery/ui/grid_view/nav_section.py``):

* ``extra_keys`` opts Left/Right in — the manager routes all four arrows here;
* ``owns`` claims only the row's live chips, so the shelf host, the dialog and
  everything else stay with their own sections;
* ``navigate`` moves within the current visual row (Left/Right) or to the
  nearest-x chip of the adjacent visual row (Up/Down), and returns ``False``
  at an edge — no wrap, no cross-row hop for Left/Right;
* the row model is re-derived from the chips' CURRENT laid-out positions on
  every call, never from a cached column count, so a resize or UI-scale change
  cannot send focus to a chip of the old wrap.

Registration is a composition, not a second registry entry. The recents shelf
is one of the picker's *declared rows*: the dialog registers a single
``ToolbarRowsSection`` over picker / fields / recents / actions
(``picker_dialog.declare_navigation_rows``), and ``NavigationManager`` has no
way to slot another section *between two rows of that section*. A separate
``RecentsGridNavSection`` registration would therefore sit next to the row
section instead of inside it: its vertical edge would hand off to
``focus_first``/``focus_last`` of the whole picker (landing on the picker row
or the action buttons) rather than the row directly above/below, and its
Left/Right edge would fall through to the row section's linear x-walk — the
original cross-row hop. ``register_recents_grid`` instead swaps the dialog's
section for ``_RecentsAwareRowsSection``, a ``ToolbarRowsSection`` that
delegates the recents chips to the grid and keeps the inherited row walk for
the block's vertical exits. ``unregister_recents_grid`` puts the original
section back, so the dialog can be closed/reused without a behavioural leak.

Audit-Meta: pattern=nav-section reason="recents shelf is a 2D grid, not one navigation row"
"""

from __future__ import annotations

import logging

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection

from ui.widgets.color.recents import RecentColorsRow

logger = logging.getLogger("ImproveImgSLI")

#: Dialog attribute holding the registered grid section (idempotent register).
SECTION_ATTR = "_recents_grid_nav_section"

_HORIZONTAL = (Qt.Key.Key_Left, Qt.Key.Key_Right)
_VERTICAL = (Qt.Key.Key_Up, Qt.Key.Key_Down)


def _identity_index(items: list[QWidget], widget: QWidget) -> int:
    """Index of *widget* by identity (``QWidget.__eq__`` is not guaranteed)."""
    for index, item in enumerate(items):
        if item is widget:
            return index
    return -1


def _center_x(widget: QWidget) -> float:
    try:
        return float(widget.x()) + widget.width() / 2.0
    except Exception:
        return 0.0


def _focus_reason() -> Qt.FocusReason:
    """App-wide focus-reason policy (mouse vs keyboard modality)."""
    try:
        from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

        return focus_reason()
    except Exception:
        return Qt.FocusReason.OtherFocusReason


class RecentsGridNavSection:
    """The recents shelf's chips as a real 2D navigation grid.

    Mirrors ``GalleryGridNavSection``: the manager calls :meth:`navigate` for
    all four arrows while a chip is focused. Left/Right step inside the
    current VISUAL row and Up/Down land on the adjacent visual row's
    horizontally nearest chip; both decline at an edge (``False``) instead of
    wrapping, so the containing section can take the key (see the module
    docstring for why the block's vertical exits are delegated instead of
    yielding to a neighbouring *registry* section).
    """

    def __init__(self, row: RecentColorsRow, *, tag: str = "color-picker-recents") -> None:
        self._row = row
        self._tag = tag

    @property
    def row(self) -> RecentColorsRow:
        """The shelf this section navigates."""
        return self._row

    @property
    def extra_keys(self) -> frozenset[int]:
        # A 2D grid legitimately maps all four arrows spatially; the manager
        # leaves Left/Right to native handlers unless a section opts in.
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})

    def _rows(self) -> list[list[QWidget]]:
        """Visual chip rows, re-derived from live geometry on every call."""
        try:
            return [list(row) for row in self._row.chip_rows()]
        except Exception:
            return []

    def owns(self, widget) -> bool:
        """Only this shelf's live chips — never the host, dialog or siblings."""
        try:
            if not shiboken6.isValid(widget):  # type: ignore[attr-defined]
                return False
            return any(widget is chip for chip in self._row.live_chips())
        except Exception:
            return False

    def navigate(self, key: int, widget) -> bool:
        if not self.owns(widget):
            return False
        rows = self._rows()
        current = next(
            (index for index, row in enumerate(rows) if _identity_index(row, widget) >= 0),
            -1,
        )
        if current < 0:
            return False

        if key in _HORIZONTAL:
            row = rows[current]
            position = _identity_index(row, widget)
            target = position + (1 if key == Qt.Key.Key_Right else -1)
            if not 0 <= target < len(row):
                # Row edge: no wrap and no hop into another visual row.
                return False
            return self._focus(row[target], _focus_reason())

        if key in _VERTICAL:
            target_row = current + (1 if key == Qt.Key.Key_Down else -1)
            if not 0 <= target_row < len(rows):
                # Top/bottom of the block: decline so the containing section's
                # row walk can leave the block (no wrap).
                return False
            return self._focus(
                self._nearest_x(rows[target_row], _center_x(widget)), _focus_reason()
            )

        return False

    def _nearest_x(self, row: list[QWidget], ref_x: float) -> QWidget:
        """Nearest chip by x-center; ties go to the left one (smaller x)."""
        return min(row, key=lambda chip: (abs(_center_x(chip) - ref_x), _center_x(chip)))

    def _focus(self, chip: QWidget, reason: Qt.FocusReason) -> bool:
        try:
            chip.setFocus(reason)
        except Exception:
            return False
        return True

    def focus_first(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        rows = self._rows()
        if not rows:
            return False
        if ref_x is None:
            return self._focus(rows[0][0], reason)
        return self._focus(self._nearest_x(rows[0], ref_x), reason)

    def focus_last(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        rows = self._rows()
        if not rows:
            return False
        if ref_x is None:
            return self._focus(rows[-1][-1], reason)
        return self._focus(self._nearest_x(rows[-1], ref_x), reason)


class _RecentsAwareRowsSection(ToolbarRowsSection):
    """The picker's declared rows, with its recents row delegated to the grid.

    Everything key-related beyond the recents chips is the inherited toolkit
    row section's: it owns the four band containers in visual order, steps
    Left/Right inside the picker / fields / actions rows and crosses Up/Down
    between them. Only the recents chips are carved out:

    * all four arrows go to :class:`RecentsGridNavSection` (its own 2D model);
    * a declined Up/Down (block edge) falls back to the inherited row walk, so
      Up leaves to the fields row and Down to the action buttons — the
      neighbouring rows live in this same section, so the manager cannot hand
      the key off to them by registry adjacency;
    * a declined Left/Right (visual row edge) stays declined, so the inherited
      linear x-walk — which would hop into the next visual row — never runs.
    """

    def __init__(self, base: ToolbarRowsSection, grid: RecentsGridNavSection) -> None:
        super().__init__(
            getattr(base, "_rows_provider", lambda: []),
            tag=getattr(base, "_tag", "color-picker"),
        )
        self._base = base
        self._grid = grid

    def navigate(self, key: int, widget) -> bool:
        if self._grid.owns(widget):
            if key in _HORIZONTAL:
                return self._grid.navigate(key, widget)
            if key in _VERTICAL and self._grid.navigate(key, widget):
                return True
        return super().navigate(key, widget)


def _registered_spec(manager, dialog):
    """The section currently registered for *dialog*, if any.

    Read-only lookup over the manager's live registry (the same structure
    ``nav_graph.snapshot`` and ``core.control.nav_state`` read); the toolkit
    exposes no public accessor and ``register`` refuses a second entry for the
    same owner.
    """
    try:
        for owner, spec in getattr(manager, "_sections", ()):
            if owner is dialog:
                return spec
    except Exception:
        pass
    return None


def register_recents_grid(
    dialog,
    row: RecentColorsRow,
    *,
    tag: str = "color-picker-recents",
) -> RecentsGridNavSection:
    """Make *row* a 2D grid inside *dialog*'s navigation section (idempotent).

    Called right after the dialog's ``declare_navigation_rows(...)``: the
    declared-rows section is swapped for a recents-aware one that delegates
    the chips to the grid (see the module docstring). Fail-open — navigation
    is an enhancement, never a reason for the picker to fail to open.
    """
    grid = getattr(dialog, SECTION_ATTR, None)
    if not isinstance(grid, RecentsGridNavSection) or grid.row is not row:
        grid = RecentsGridNavSection(row, tag=tag)
        try:
            setattr(dialog, SECTION_ATTR, grid)
        except Exception:
            pass
    try:
        manager = NavigationManager.get_instance()
        spec = _registered_spec(manager, dialog)
        if isinstance(spec, _RecentsAwareRowsSection):
            # Keep the wrapper, refresh the grid row binding, re-register so
            # the section survives a caller that dropped it in between.
            spec._grid = grid
            manager.unregister(dialog)
            manager.register(dialog, spec)
        elif isinstance(spec, ToolbarRowsSection):
            manager.unregister(dialog)
            manager.register(dialog, _RecentsAwareRowsSection(spec, grid))
        elif spec is None:
            # The dialog declared no rows yet (call order violated): register
            # the grid under the shelf so the chips are still navigable. The
            # vertical exits cannot work until a rows section exists.
            manager.register(row, grid)
    except Exception:
        logger.debug("recents grid navigation not registered", exc_info=True)
    return grid


def unregister_recents_grid(dialog) -> None:
    """Drop the grid and restore the picker's original declared-rows section."""
    try:
        grid = getattr(dialog, SECTION_ATTR, None)
        manager = NavigationManager.get_instance()
        if isinstance(grid, RecentsGridNavSection):
            manager.unregister(grid.row)
        spec = _registered_spec(manager, dialog)
        if isinstance(spec, _RecentsAwareRowsSection):
            manager.unregister(dialog)
            base = getattr(spec, "_base", None)
            if base is not None:
                manager.register(dialog, base)
        try:
            setattr(dialog, SECTION_ATTR, None)
        except Exception:
            pass
    except Exception:
        logger.debug("recents grid navigation not unregistered", exc_info=True)


__all__ = [
    "RecentsGridNavSection",
    "SECTION_ATTR",
    "register_recents_grid",
    "unregister_recents_grid",
]
