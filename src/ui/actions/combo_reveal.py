"""Open a toolkit ComboBox dropdown after host UI has settled.

Find Action closes (and Settings first-show) emit Hide / WindowDeactivate /
geometry events. ComboBox installs an app-wide filter while expanded and
collapses on those events — so a synchronous ``showDropdown()`` right after
``ensure_visible`` often fails until the window has settled.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer


class _PulseDeferred:
    """Sentinel: dropdown will pulse its own row when ready; skip field pulse."""


def _is_valid(obj) -> bool:
    if obj is None:
        return False
    try:
        import shiboken6

        return bool(shiboken6.isValid(obj))
    except Exception:
        return True


def select_combo_index(combo, index: int) -> None:
    """Commit ``index`` when in range (updates the closed-field label)."""
    if not _is_valid(combo):
        return
    set_index = getattr(combo, "setCurrentIndex", None)
    count_fn = getattr(combo, "count", None)
    count = int(count_fn()) if callable(count_fn) else 0
    if callable(set_index) and 0 <= index < count:
        set_index(index)


def dropdown_row_widget(combo, index: int):
    """Visible dropdown row for ``index``, or ``None``."""
    if not _is_valid(combo):
        return None
    getter = getattr(combo, "dropdown_row_widget", None)
    if callable(getter):
        row = getter(index)
        if row is not None:
            return row
    overlay = getattr(combo, "_overlay", None)
    if overlay is None:
        return None
    slot_for = getattr(overlay, "slot_for_index", None)
    if callable(slot_for):
        return slot_for(index)
    for slot in getattr(overlay, "_slots", ()) or ():
        if getattr(slot, "isVisible", lambda: False)() and getattr(
            slot, "_item_index", -1
        ) == index:
            return slot
    return None


def _pulse_dropdown_row(combo, index: int) -> None:
    from ui.actions import widget_pulse

    row = dropdown_row_widget(combo, index)
    if row is not None:
        widget_pulse.pulse_widget(row)


def _open_dropdown(combo, *, focus_index: int | None) -> bool:
    show = getattr(combo, "showDropdown", None)
    if not callable(show):
        return False
    try:
        if focus_index is None:
            show()
        else:
            show(focus_index=focus_index)
    except TypeError:
        show()
    expanded = bool(getattr(combo, "_expanded", False))
    overlay = getattr(combo, "_overlay", None)
    overlay_ok = overlay is not None and (
        not hasattr(overlay, "isVisible") or overlay.isVisible()
    )
    return expanded and overlay_ok


def schedule_combo_dropdown(
    combo,
    *,
    focus_index: int | None = None,
    attempts: int = 10,
    interval_ms: int = 40,
    on_ready=None,
) -> None:
    """Open ``combo``'s dropdown, retrying until the host window has settled."""
    if not _is_valid(combo):
        return

    state = {"left": max(1, int(attempts))}

    def _try() -> None:
        state["left"] -= 1
        if not _is_valid(combo):
            return
        if not combo.isVisible():
            if state["left"] > 0:
                QTimer.singleShot(interval_ms, _try)
            return
        window = combo.window()
        if window is None or not _is_valid(window) or not window.isVisible():
            if state["left"] > 0:
                QTimer.singleShot(interval_ms, _try)
            return

        if _open_dropdown(combo, focus_index=focus_index):
            if callable(on_ready):
                on_ready()
            return
        if state["left"] > 0:
            QTimer.singleShot(interval_ms, _try)

    QTimer.singleShot(0, _try)


def reveal_combo_option(combo, index: int) -> object:
    """Open the dropdown on ``index`` and return the row to pulse (or defer)."""
    if _is_valid(combo) and combo.isVisible():
        window = combo.window()
        if window is not None and window.isVisible() and _open_dropdown(
            combo, focus_index=index
        ):
            row = dropdown_row_widget(combo, index)
            if row is not None:
                return row

    schedule_combo_dropdown(
        combo,
        focus_index=index,
        on_ready=lambda c=combo, i=index: _pulse_dropdown_row(c, i),
    )
    return _PulseDeferred()


def select_combo_option(combo, index: int) -> object:
    """Commit ``index`` and open the dropdown; return the row to pulse."""
    select_combo_index(combo, index)
    return reveal_combo_option(combo, index)


def prepare_combo_option(combo, index: int, *, apply: bool = False) -> object:
    """Reveal (default) or select+reveal a combo option for Find Action."""
    if apply:
        return select_combo_option(combo, index)
    return reveal_combo_option(combo, index)
