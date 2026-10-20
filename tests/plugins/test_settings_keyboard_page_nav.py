"""Settings → Keyboard page: every control is a row of the page's row model.

The page used to add two controls straight to the page layout instead of going
through ``page_nav_builder``/``NavRowBuilder``: the "Filter shortcuts" field
(above the chord rows) and the "Reset all shortcuts" button (below them, built
after ``builder.extend``). Both were therefore outside every row the page's
``ToolbarRowsSection`` owns — keyboard-coverage finding F2, pinned in
``tests/nav_coverage_allowlist.py`` as ``SettingsDialog:CustomLineEdit`` and
``SettingsDialog:Button``.

Falsification story (recorded in DONE.md): with the pre-fix tree
``test_filter_and_reset_all_are_owned`` fails (neither control has a section
owner) and ``test_down_walks_filter_to_reset_all_and_up_returns`` fails on the
very first Down (focus leaves the filter onto a chord row, so the walk never
meets Reset all). The fix puts both controls into the builder in visual order
(filter → chord rows → Reset all), which makes both green and lets the F2
allowlist entries be deleted (the contract then reports them owned, not
exempt).

Offscreen, real ``SettingsDialog`` + the process-wide ``NavigationManager``;
keys go through ``QTest.keyClick`` so the manager's QApplication event filter
(not a direct widget event) is what actually routes the arrows.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from resources.translations import add_i18n_root
from sli_ui_toolkit.managers import NavigationManager

_I18N_ROOT = Path(__file__).resolve().parents[2] / "src/plugins/settings/resources/i18n"


def _manager() -> NavigationManager:
    return NavigationManager.get_instance()


def _owns(widget: QWidget) -> bool:
    """True when some registered section claims *widget* (live registry)."""
    for _owner, spec in list(_manager()._sections):
        try:
            if spec.owns(widget):
                return True
        except Exception:
            continue
    return False


def _pump(rounds: int = 3) -> None:
    app = QApplication.instance()
    for _ in range(rounds):
        app.processEvents()


def _keyboard_dialog():
    add_i18n_root(_I18N_ROOT)
    from plugins.settings.dialog import SettingsDialog

    dialog = SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        active_tab="image_compare",
    )
    dialog.show()
    _pump()
    dialog.select_section("builtin.keyboard")
    _pump(6)
    return dialog


def _kbd_focus(widget: QWidget) -> None:
    widget.setFocus(_manager().current_focus_reason())
    _pump()


def _press(key: Qt.Key) -> QWidget | None:
    focused = QApplication.focusWidget()
    assert focused is not None, "nothing focused — cannot drive the page"
    QTest.keyClick(focused, key)
    _pump()
    return QApplication.focusWidget()


@pytest.fixture()
def keyboard_dialog(qapp):
    dialog = _keyboard_dialog()
    try:
        yield dialog
    finally:
        dialog.close()
        dialog.deleteLater()
        _pump()


def test_filter_and_reset_all_are_owned(keyboard_dialog):
    """Both F2 controls are claimed by the page's own row section."""
    filter_edit = keyboard_dialog._keyboard_search
    reset_all = keyboard_dialog._keyboard_reset_all
    assert _owns(filter_edit), (
        "the Filter shortcuts field is an orphan — no section owns it"
    )
    assert _owns(reset_all), (
        "the Reset all shortcuts button is an orphan — no section owns it"
    )
    # Same section owns them as the chord rows (one row model, not a second
    # registration path).
    owners = [
        spec
        for _owner, spec in list(_manager()._sections)
        if spec.owns(filter_edit)
    ]
    assert len(owners) == 1, f"filter owned by {len(owners)} sections"
    assert owners[0] is getattr(
        keyboard_dialog, "_settings_keyboard_nav_section"
    ), "the filter must be owned by the keyboard page's own row section"
    assert owners[0].owns(reset_all)


def test_row_model_matches_visual_order(keyboard_dialog):
    """Filter is above every chord row; Reset all is below every chord row."""
    filter_edit = keyboard_dialog._keyboard_search
    reset_all = keyboard_dialog._keyboard_reset_all

    def _top(widget: QWidget) -> int:
        return widget.mapToGlobal(widget.rect().topLeft()).y()

    def _bottom(widget: QWidget) -> int:
        return widget.mapToGlobal(widget.rect().bottomLeft()).y()

    captures = list(keyboard_dialog._keyboard_capture_rows.values())
    assert captures, "the page built no chord rows"
    for capture in captures:
        assert _owning_row_top(capture) >= _top(filter_edit)
        assert _owning_row_top(capture) > _bottom(filter_edit)
        assert _top(reset_all) > _bottom(capture)


def _owning_row_top(widget: QWidget) -> int:
    """Top edge of the nav row that contains *widget*."""
    for _owner, spec in list(_manager()._sections):
        try:
            row = spec._row_of(widget)
        except Exception:
            continue
        if row is not None:
            return row.mapToGlobal(row.rect().topLeft()).y()
    raise AssertionError(f"{type(widget).__name__} has no owning nav row")


def test_down_walks_filter_to_reset_all_and_up_returns(keyboard_dialog):
    """Down: filter → first chord row → … → Reset all; Up walks back."""
    filter_edit = keyboard_dialog._keyboard_search
    reset_all = keyboard_dialog._keyboard_reset_all
    captures = set(keyboard_dialog._keyboard_capture_rows.values())

    _kbd_focus(filter_edit)
    assert QApplication.focusWidget() is filter_edit

    visited: list[QWidget] = []
    current = filter_edit
    for _ in range(400):
        nxt = _press(Qt.Key.Key_Down)
        assert nxt is not None, "Down dropped focus to nothing"
        assert nxt is not current, (
            f"Down stalled on {type(current).__name__} — row model disagrees "
            "with the page's visual rows"
        )
        assert _owns(nxt), f"Down moved onto an orphan: {type(nxt).__name__}"
        current = nxt
        visited.append(current)
        if current is reset_all:
            break
    else:  # pragma: no cover - defensive bound
        pytest.fail("Down never reached Reset all shortcuts")

    # The walk stepped through real chord rows (not filter → Reset all direct)
    assert captures.intersection(visited), (
        "Down skipped the chord rows — the filter must be their row-predecessor"
    )

    back: list[QWidget] = []
    for _ in range(400):
        prev = _press(Qt.Key.Key_Up)
        assert prev is not None, "Up dropped focus to nothing"
        assert prev is not current, (
            f"Up stalled on {type(current).__name__}"
        )
        assert _owns(prev), f"Up moved onto an orphan: {type(prev).__name__}"
        current = prev
        back.append(current)
        if current is filter_edit:
            break
    else:  # pragma: no cover - defensive bound
        pytest.fail("Up never walked back to the filter field")

    # Up retraced the same row sequence in reverse.
    assert back[:-1] == visited[:-1][::-1]


def test_reset_all_still_resets_overrides(keyboard_dialog):
    """Behaviour unchanged: the button clears overrides after the move."""
    from ui.actions.keymap import effective_shortcut_for_id

    dialog = keyboard_dialog
    dialog._keyboard_overrides["image_compare.diff_mode"] = "Ctrl+9"
    dialog._keyboard_reset_all.click()
    _pump()
    assert (
        effective_shortcut_for_id(
            "image_compare.diff_mode",
            default="H",
            overrides=dialog._keyboard_overrides,
        )
        == "H"
    )
