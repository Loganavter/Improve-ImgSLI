"""Keyboard-navigation section for the unified list picker's two list panels.

Audit-Meta: pattern=nav-section reason="two side-by-side list panels are a real 2D focus grid"

The picker is a plain ``QWidget`` overlay (not a toolkit ``BaseFlyout``), so it
has no built-in keyboard section: every row Button and both panels were
arrow-unreachable while the keyboard cursor sat on the opener (audit rank 1,
2026-10-19).

Model — the gallery's real-2D sibling, not the toolkit's auto section and not
one ``ToolbarRowsSection``:

* Both panels are visible at once, side by side. The toolkit auto section
  groups every StrongFocus leaf into y-bands, which is the right *horizontal*
  model, but it CONSUMES Up at its top row and Down at its bottom row, so the
  picker would trap the keyboard cursor instead of handing it back to the
  tab/toolbar that opened it.
* ``declare_navigation_rows(owner, [panel_left, panel_right])`` treats the
  panels as vertical rows: Down would hop between the panels and Left/Right
  would walk one panel linearly — the wrong axes for a side-by-side layout.

So the section mirrors ``tabs/image_gallery/ui/grid_view/nav_section.py``
(``extra_keys`` opts Left/Right in; ``owns`` claims only live cells; edges
return ``False`` — no wrap — so ``NavigationManager`` trial-dispatches to the
neighbouring section). Row bands are the shared ``group_visual_rows`` model
the flyouts and ``AutoNavigationSection`` use, so a band always means "same
visual row across both panels":

* Down/Up walk rows **inside the focused panel** and land on the horizontally
  nearest cell of the next/previous row; at the panel's first/last row they
  decline (``False``) for the host section to take the key.
* Left/Right walk the current visual band in x order, which is exactly what
  carries focus across the panel gap once the band's left panel is exhausted;
  at a band edge they decline instead of wrapping.

Lifecycle follows the ``BaseFlyout`` precedent: the section is registered in
``showEvent`` and unregistered in ``hideEvent`` (plus on ``destroyed``), so a
closed picker never keeps a section in the app-wide registry.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QWidget

from sli_ui_toolkit.managers import NavigationManager
from sli_ui_toolkit.ui.managers.nav_rows import group_visual_rows

__all__ = [
    "UnifiedListNavSection",
    "register_picker_navigation",
    "unregister_picker_navigation",
]

_HORIZONTAL = frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})


def _focus_reason() -> Qt.FocusReason:
    """App-wide keyboard/mouse modality policy (not a fixed reason)."""
    try:
        from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

        return focus_reason()
    except Exception:
        return Qt.FocusReason.OtherFocusReason


def _scroll_into_view(widget: QWidget) -> None:
    """Scroll *widget*'s nearest ``QScrollArea`` so it is on screen.

    Fallback for panels that are not virtual-list hosts (no row ``index`` to
    hand the controller); virtual hosts use ``_focus``, which avoids a second,
    pool-corrupting scroll.
    """
    try:
        area: QWidget | None = widget.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if isinstance(area, QScrollArea):
            area.ensureWidgetVisible(widget, 0, 40)
    except Exception:
        pass


def _global_x(widget: QWidget) -> float:
    try:
        return float(widget.mapToGlobal(widget.rect().center()).x())
    except Exception:
        return 0.0


def _global_y(widget: QWidget) -> float:
    try:
        return float(widget.mapToGlobal(widget.rect().center()).y())
    except Exception:
        return 0.0


def _contains(items: list[QWidget], widget: QWidget) -> bool:
    """Identity membership (``QWidget.__eq__`` is not a guaranteed identity)."""
    return any(item is widget for item in items)


class UnifiedListNavSection:
    """``sli_ui_toolkit.managers.navigation_manager.NavigationSection`` for the picker.

    Registered by :func:`register_picker_navigation` while the picker is
    visible; see the module docstring for the axes model and edge policy.
    """

    def __init__(self, picker: QWidget) -> None:
        self._picker = picker

    @property
    def extra_keys(self) -> frozenset[int]:
        # A 2D layout legitimately maps Left/Right spatially (across the panel
        # gap). NavigationManager leaves horizontal keys to native handlers
        # unless a section owning the focused widget opts in.
        return _HORIZONTAL

    # ------------------------------------------------------------------
    # Widget-tree discovery (always live — rows are rebuilt per open)
    # ------------------------------------------------------------------

    def _panels(self) -> list[QWidget]:
        panels: list[QWidget] = []
        try:
            for attr in ("panel_left", "panel_right"):
                panel = getattr(self._picker, attr, None)
                if not isinstance(panel, QWidget):
                    continue
                if panel.isVisible():
                    panels.append(panel)
        except RuntimeError:
            # Owner's C++ side was torn down before its section unregistered.
            return []
        return panels

    @staticmethod
    def _cells(panel: QWidget) -> list[QWidget]:
        """StrongFocus leaves inside the panel's row area.

        Starts from ``content_widget`` (the virtual-list row host) rather than
        the panel or scroll area: ``QScrollArea`` itself is StrongFocus and
        visible, and claiming it would put a phantom cell in every band. Rows
        and their nested +/- steppers are the only interactive descendants.
        """
        content = getattr(panel, "content_widget", None)
        if not isinstance(content, QWidget):
            return []
        try:
            candidates = content.findChildren(QWidget)
        except RuntimeError:
            return []
        cells: list[QWidget] = []
        for widget in candidates:
            try:
                if widget is content or not shiboken6.isValid(widget):
                    continue
                if widget.focusPolicy() != Qt.FocusPolicy.StrongFocus:
                    continue
                if not widget.isVisible() or not widget.isEnabled():
                    continue
            except RuntimeError:
                continue
            cells.append(widget)
        return cells

    def _panel_of(self, widget: QWidget) -> QWidget | None:
        for panel in self._panels():
            try:
                if panel is widget or panel.isAncestorOf(widget):
                    return panel
            except RuntimeError:
                continue
        return None

    def _panel_rows(self, panel: QWidget) -> list[list[QWidget]]:
        return group_visual_rows(self._cells(panel))

    def _band_rows(self) -> list[list[QWidget]]:
        cells: list[QWidget] = []
        for panel in self._panels():
            cells.extend(self._cells(panel))
        return group_visual_rows(cells)

    def _band_of(self, widget: QWidget) -> list[QWidget] | None:
        for band in self._band_rows():
            if _contains(band, widget):
                return band
        return None

    @staticmethod
    def _row_widget(band: list[QWidget]) -> QWidget | None:
        """The row host of a band (the ``ListPanel`` row protocol's ``index``)."""
        for cell in band:
            if getattr(cell, "index", None) is not None:
                return cell
        return None

    @staticmethod
    def _row_cells(row: QWidget) -> list[QWidget]:
        """The row host plus its own focusable children (its +/- steppers)."""
        cells = [row]
        try:
            children = row.findChildren(QWidget)
        except RuntimeError:
            children = []
        for child in children:
            try:
                if not shiboken6.isValid(child):
                    continue
                if child.focusPolicy() != Qt.FocusPolicy.StrongFocus:
                    continue
                if not child.isVisible() or not child.isEnabled():
                    continue
            except RuntimeError:
                continue
            cells.append(child)
        cells.sort(key=_global_x)
        return cells

    def _all_cells(self) -> list[QWidget]:
        cells: list[QWidget] = []
        for panel in self._panels():
            cells.extend(self._cells(panel))
        return cells

    # ------------------------------------------------------------------
    # Section protocol
    # ------------------------------------------------------------------

    def owns(self, widget: QWidget) -> bool:
        """Only live interactive cells — never the panels or the host."""
        try:
            return _contains(self._all_cells(), widget)
        except Exception:
            return False

    def navigate(self, key: int, widget: QWidget) -> bool:
        reason = _focus_reason()
        panel = self._panel_of(widget)
        if panel is not None and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            rows = self._panel_rows(panel)
            index = next(
                (i for i, row in enumerate(rows) if _contains(row, widget)),
                None,
            )
            if index is None:
                return False
            delta = 1 if key == Qt.Key.Key_Down else -1
            target = index + delta
            if 0 <= target < len(rows):
                return self._focus_nearest_x(rows[target], widget, reason)
            # Beyond the materialized rows: the panel is a virtual list (only
            # the visible window plus overscan exists as widgets), so scroll
            # one item and focus the row the controller just bound.
            return self._step_virtual_row(panel, rows, index, delta, widget, reason)

        if key in _HORIZONTAL:
            band = self._band_of(widget)
            if band is None:
                return False
            position = next(
                (i for i, cell in enumerate(band) if cell is widget),
                None,
            )
            if position is None:
                return False
            target = position + (1 if key == Qt.Key.Key_Right else -1)
            if not 0 <= target < len(band):
                # Band edge: no wrap into the neighbouring row/panel.
                return False
            return self._focus(band[target], reason)

        return False

    def focus_first(
        self, ref_x: float | None = None, *, reason: Qt.FocusReason
    ) -> bool:
        bands = self._band_rows()
        if not bands:
            return False
        return self._focus_in_band(bands[0], ref_x, reason)

    def focus_last(
        self, ref_x: float | None = None, *, reason: Qt.FocusReason
    ) -> bool:
        bands = self._band_rows()
        if not bands:
            return False
        return self._focus_in_band(bands[-1], ref_x, reason)

    def focus_nearest(self, pos, *, reason: Qt.FocusReason) -> bool:
        """Click-driven re-anchor: the cell closest to the click point."""
        cells = self._all_cells()
        if not cells:
            return False
        try:
            point = pos.toPoint() if hasattr(pos, "toPoint") else pos
            px, py = float(point.x()), float(point.y())
        except Exception:
            return self.focus_first(reason=reason)
        target = min(
            cells,
            key=lambda w: abs(_global_x(w) - px) + abs(_global_y(w) - py),
        )
        return self._focus(target, reason)

    # ------------------------------------------------------------------
    # Focus primitives
    # ------------------------------------------------------------------

    @staticmethod
    def _row_host_of(widget: QWidget) -> QWidget | None:
        """Climb to the row host (the widget carrying ``ListPanel``'s ``index``)."""
        current: QWidget | None = widget
        for _ in range(8):
            if current is None:
                return None
            if getattr(current, "index", None) is not None:
                return current
            current = current.parentWidget()
        return None

    def _focus(self, widget: QWidget, reason: Qt.FocusReason) -> bool:
        """Focus *widget*, scrolling its virtual row into view when needed.

        The scroll is delegated to the panel's virtual-list controller, never
        to ``QScrollArea.ensureWidgetVisible`` (a second scroll after the
        controller already positioned the row). A real scroll is followed by a
        forced rebind: the pool's reuse pass keeps index→slot assignments but
        hides by slot POSITION, so a shrinking window can hide a still-live
        index (measured: the arrow walk skipped rows and then lost focus to the
        picker, whose next press re-bootstrapped = a wrap). After a forced
        rebind the widget→index binding may have moved, so the target is
        re-resolved by the same index and the same screen column.
        """
        row_host = self._row_host_of(widget)
        index = getattr(row_host, "index", None)
        panel = self._panel_of(widget)
        controller = getattr(panel, "_controller", None) if panel is not None else None
        if row_host is None or index is None or controller is None:
            _scroll_into_view(widget)
        else:
            ref_x = _global_x(widget)
            try:
                before = controller.scroll_offset
                controller.ensure_visible(int(index))
                if controller.scroll_offset != before:
                    controller.rebind(force=True)
                    replacement = controller.widget_for_index(int(index))
                    if replacement is not None:
                        widget = min(
                            self._row_cells(replacement),
                            key=lambda w: abs(_global_x(w) - ref_x),
                        )
            except Exception:
                _scroll_into_view(widget)
        try:
            widget.setFocus(reason)
        except RuntimeError:
            return False
        return True

    def _focus_nearest_x(
        self, band: list[QWidget], reference: QWidget, reason: Qt.FocusReason
    ) -> bool:
        if not band:
            return False
        ref_x = _global_x(reference)
        target = min(band, key=lambda w: abs(_global_x(w) - ref_x))
        return self._focus(target, reason)

    def _step_virtual_row(
        self,
        panel: QWidget,
        rows: list[list[QWidget]],
        index: int,
        delta: int,
        reference: QWidget,
        reason: Qt.FocusReason,
    ) -> bool:
        """Vertical edge of the materialized window: scroll one row, focus it.

        ``ListPanel`` virtualizes rows (only the visible window plus overscan
        exists as widgets), so the last live row is not necessarily the last
        item. Scrolling by one item and rebinding keeps Down/Up walking the
        whole list; at the true first/last item the controller has nowhere to
        go and this declines, so the host section takes the key.
        """
        row_widget = self._row_widget(rows[index])
        controller = getattr(panel, "_controller", None)
        current = getattr(row_widget, "index", None)
        if controller is None or current is None:
            return False
        wanted = int(current) + delta
        try:
            count = int(controller.count())
        except Exception:
            return False
        if not 0 <= wanted < count:
            return False
        try:
            before = controller.scroll_offset
            controller.ensure_visible(wanted)
            if controller.scroll_offset != before:
                # Normalize the pool after a real scroll: a reuse rebind keeps
                # index→slot assignments but its cleanup hides by slot
                # POSITION, which can hide still-live in-window indices (the
                # walk then skipped rows and eventually lost focus). A forced
                # rebind re-binds every in-window slot to its index in order.
                rebind = getattr(controller, "rebind", None)
                if callable(rebind):
                    rebind(force=True)
        except RuntimeError:
            return False
        target = controller.widget_for_index(wanted)
        if target is None:
            return False
        return self._focus_nearest_x(self._row_cells(target), reference, reason)

    def _focus_in_band(
        self, band: list[QWidget], ref_x: float | None, reason: Qt.FocusReason
    ) -> bool:
        if not band:
            return False
        if ref_x is None:
            return self._focus(band[0], reason)
        target = min(band, key=lambda w: abs(_global_x(w) - ref_x))
        return self._focus(target, reason)


def register_picker_navigation(picker: QWidget) -> UnifiedListNavSection | None:
    """Register the picker's section (idempotent); returns the live section."""
    existing = getattr(picker, "_nav_section", None)
    if existing is not None:
        return existing
    try:
        section = UnifiedListNavSection(picker)
        NavigationManager.get_instance().register(picker, section)
    except Exception:
        return None
    picker._nav_section = section  # type: ignore[attr-defined]
    return section


def unregister_picker_navigation(picker: QWidget) -> None:
    """Drop the picker's section, if registered (safe on a destroyed owner)."""
    if getattr(picker, "_nav_section", None) is None:
        return
    try:
        NavigationManager.get_instance().unregister(picker)
    except Exception:
        pass
    try:
        picker._nav_section = None  # type: ignore[attr-defined]
    except RuntimeError:
        pass
