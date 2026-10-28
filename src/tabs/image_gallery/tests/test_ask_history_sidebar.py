"""Ask AI history list + tab-level sidebar host (offscreen).

Falsification: pre-change the gallery had no history list (only the
"N previous questions" count) and no sidebar host at all — the ask surface was
the flyout itself, so there was nothing to embed. These tests fail on that
build: ``AskAiSurface``/``AskAiSidebar`` do not exist, the log records are not
rendered, and no section owns a history row or the sidebar toggle.

Hermetic: ``IMGSLI_PROJECT_CACHE`` points the ask log at ``tmp_path`` (same
override ``test_ask_log.py`` uses), so the real user cache is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.services import ask_log
from tabs.image_gallery.services.ask_context import AskScope
from tabs.image_gallery.ui import ask_nav
from tabs.image_gallery.ui.ask_sidebar import AskAiSidebar
from tabs.image_gallery.ui.ask_surface import AskAiSurface
from tabs.image_gallery.widget import ImageGalleryWidget

_SCOPE_PATH = Path("/gallery/a.png")


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("IMGSLI_PROJECT_CACHE", str(tmp_path / "cache"))
    return tmp_path


def _seed_log(count: int) -> None:
    for index in range(count):
        ask_log.append_answer(
            scope_kind="selection",
            scope_label="Selection",
            paths=[str(_SCOPE_PATH)],
            question=f"question {index}",
            answer=f"answer {index}",
            model="openai/gpt-4o",
            base_url="https://api.example.test/v1",
            cache_hit=False,
        )


def _widget(qtbot) -> ImageGalleryWidget:
    widget = ImageGalleryWidget()
    qtbot.addWidget(widget)
    widget.resize(900, 600)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _anchor(qtbot) -> QWidget:
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(160, 90)
    anchor.show()
    qtbot.waitExposed(anchor)
    return anchor


def _open_flyout(qtbot, widget):
    scope = AskScope(kind="selection", paths=(_SCOPE_PATH,), label="Selection")
    widget.open_ask_ai(_anchor(qtbot), scope)
    flyout = widget._ensure_ask_ai_flyout()
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    # Past the show fade: BaseFlyout keeps children hidden while fading, so a
    # section's row scan is empty until the fade finishes.
    qtbot.wait(350)
    return flyout


def _focused(widget):
    """The window's focus widget (``QApplication.focusWidget`` is None offscreen)."""
    try:
        return widget.focusWidget() or QApplication.focusWidget()
    except Exception:
        return QApplication.focusWidget()


# -- history list -----------------------------------------------------------


def test_history_renders_seeded_exchanges_oldest_to_newest(qtbot):
    _seed_log(3)
    widget = _widget(qtbot)
    flyout = _open_flyout(qtbot, widget)
    surface = widget._ask_ai_surface

    assert surface is not None
    assert [r["question"] for r in surface._history_records] == [
        "question 0",
        "question 1",
        "question 2",
    ]
    buttons = surface.history_row_buttons()
    assert len(buttons) == 3
    # Each entry shows BOTH halves of the exchange: the question line and the
    # answer line of one focusable row.
    assert [row.text for row in buttons[0]._rows] == ["question 0", "answer 0"]
    assert "question 2" in buttons[2].toolTip()
    assert "answer 2" in buttons[2].toolTip()

    # The live pane opens on the tail (newest) exchange.
    assert surface._result.text() == "answer 2"
    assert surface._history_title.isHidden() is False
    assert surface._history_list.isHidden() is False
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_selecting_history_redisplays_answer_without_an_api_call(qtbot):
    _seed_log(3)
    widget = _widget(qtbot)
    flyout = _open_flyout(qtbot, widget)
    surface = widget._ask_ai_surface
    before = ask_log.count()

    surface.select_history(0)

    assert surface.selected_history_index() == 0
    assert surface._result.text() == "answer 0"
    assert "AI read" in surface._status.text()
    # Re-display only: the stored answer was not re-requested nor re-logged.
    assert ask_log.count() == before
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_live_answer_keeps_its_links_when_the_history_appends(qtbot):
    """A just-arrived answer keeps its clickable image links.

    Falsification: reloading the history with the newest record selected used
    to re-display the stored (link-less) record over the live answer, so the
    image links vanished the moment the answer landed.
    """
    from types import SimpleNamespace

    _seed_log(1)
    widget = _widget(qtbot)
    flyout = _open_flyout(qtbot, widget)
    surface = widget._ask_ai_surface

    answer = "Prefer Pic A.png; Pic B.png is softer."
    ask_log.append_answer(
        scope_kind="selection",
        scope_label="Selection",
        paths=[str(_SCOPE_PATH)],
        question="which is better?",
        answer=answer,
        model="openai/gpt-4o",
        base_url="https://api.example.test/v1",
    )
    widget.show_ask_ai_result(
        SimpleNamespace(text=answer, backend="text", cached=False),
        links={"Pic A.png": "/g/A.png", "Pic B.png": "/g/B.png"},
    )

    assert '<a href="gallery-image:' in surface._result.text()
    assert surface.selected_history_index() == len(surface._history_records) - 1
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_empty_history_shows_the_empty_state(qtbot):
    widget = _widget(qtbot)
    flyout = _open_flyout(qtbot, widget)
    surface = widget._ask_ai_surface

    assert surface._history_records == []
    assert surface.history_row_buttons() == []
    assert surface._history_empty.text() == "No questions yet."
    assert surface._history_empty.isHidden() is False
    assert surface._history_list.isHidden() is True
    assert surface._history_title.isHidden() is True
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_history_is_localized_when_texts_are_injected(qtbot):
    _seed_log(1)
    widget = _widget(qtbot)
    flyout = _open_flyout(qtbot, widget)
    surface = widget._ask_ai_surface
    surface.set_texts(
        history_title="История",
        history_empty="Вопросов пока нет.",
    )
    assert surface._history_title.text() == "История"

    surface.set_history_records([], show_tail=False)
    assert surface._history_empty.text() == "Вопросов пока нет."
    assert surface._history_empty.isHidden() is False
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


# -- sidebar host -----------------------------------------------------------


def test_sidebar_toggle_shows_hides_and_hosts_the_same_surface(qtbot):
    _seed_log(2)
    widget = _widget(qtbot)
    toolbar_button = widget.toolbar.ask_sidebar_button

    # Initially closed; the toolbar toggle is the workspace entry point.
    assert widget._ask_ai_sidebar is None or not widget._ask_ai_sidebar.isVisible()
    assert toolbar_button.isChecked() is False

    widget.set_ask_sidebar_visible(True)
    sidebar = widget._ask_ai_sidebar
    surface = widget._ask_ai_surface
    assert isinstance(sidebar, AskAiSidebar)
    assert sidebar.isVisible() is True
    assert toolbar_button.isChecked() is True
    assert surface is not None and isinstance(surface, AskAiSurface)
    assert sidebar.surface() is surface
    # One instance, not a second surface/flyout inside the panel.
    assert len(widget.findChildren(AskAiSurface)) == 1
    assert [r["question"] for r in surface._history_records] == [
        "question 0",
        "question 1",
    ]

    widget.set_ask_sidebar_visible(False)
    assert sidebar.isVisible() is False
    assert toolbar_button.isChecked() is False


def test_sidebar_takes_the_surface_from_the_flyout_and_back(qtbot):
    _seed_log(1)
    widget = _widget(qtbot)
    flyout = _open_flyout(qtbot, widget)
    surface = widget._ask_ai_surface
    assert flyout.surface() is surface

    widget.set_ask_sidebar_visible(True)
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)
    assert widget._ask_ai_sidebar.surface() is surface
    assert flyout.surface() is None
    # Opening an ask while the sidebar is visible retargets the docked panel
    # instead of popping a second flyout over it.
    scope = AskScope(kind="selection", paths=(_SCOPE_PATH,), label="Selection")
    widget.open_ask_ai(_anchor(qtbot), scope)
    assert flyout.isVisible() is False
    assert widget._ask_ai_sidebar.surface() is surface

    # The next flyout open takes the same instance back.
    widget.set_ask_sidebar_visible(False)
    widget.open_ask_ai(_anchor(qtbot), scope)
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    assert flyout.surface() is surface
    assert widget._ask_ai_sidebar.surface() is None
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_sidebar_close_button_hides_and_syncs_the_toolbar(qtbot):
    widget = _widget(qtbot)
    widget.set_ask_sidebar_visible(True)
    sidebar = widget._ask_ai_sidebar
    assert sidebar._close_btn.toolTip() == "Hide AI sidebar"

    sidebar._close_btn.click()

    assert sidebar.isVisible() is False
    assert widget.toolbar.ask_sidebar_button.isChecked() is False


def test_toolbar_toggle_opens_the_sidebar_by_click(qtbot):
    widget = _widget(qtbot)
    button = widget.toolbar.ask_sidebar_button

    button.click()
    assert widget._ask_ai_sidebar is not None
    assert widget._ask_ai_sidebar.isVisible() is True
    assert button.isChecked() is True
    assert button.toolTip() == "Hide AI sidebar"

    button.click()
    assert widget._ask_ai_sidebar.isVisible() is False
    assert button.isChecked() is False
    assert button.toolTip() == "Show AI sidebar"


def test_toolbar_toggle_opens_the_sidebar_from_the_keyboard(qtbot):
    """The toggle is a real keyboard control (Space), not a click-only icon."""
    widget = _widget(qtbot)
    button = widget.toolbar.ask_sidebar_button
    button.setFocus(Qt.FocusReason.OtherFocusReason)

    qtbot.keyClick(button, Qt.Key.Key_Space)

    qtbot.waitUntil(
        lambda: widget._ask_ai_sidebar is not None and widget._ask_ai_sidebar.isVisible(),
        timeout=3000,
    )
    assert button.isChecked() is True


# -- keyboard ownership -----------------------------------------------------


def test_history_rows_and_question_row_are_nav_owned(qtbot):
    _seed_log(2)
    widget = _widget(qtbot)
    widget.set_ask_sidebar_visible(True)
    sidebar = widget._ask_ai_sidebar
    surface = widget._ask_ai_surface

    section = ask_nav.section_of(sidebar)
    assert section is not None
    # Registered in the app-wide graph, not just a local object.
    from core.navigation import NavigationManager

    owners = [
        owner
        for owner, spec in NavigationManager.get_instance()._sections
        if spec is section
    ]
    assert owners == [sidebar]
    assert section.owns(surface.question_row) is True
    buttons = surface.history_row_buttons()
    assert len(buttons) == 2
    assert all(section.owns(button) for button in buttons)

    # Down: question row → first exchange → second exchange → wrap to the
    # sidebar's ✕ (visual top row), and Up from the ✕ wraps back to the newest
    # exchange. Every row — chrome, question and history — is in the walk.
    surface._edit.setFocus(Qt.FocusReason.OtherFocusReason)
    assert section.navigate(Qt.Key.Key_Down, surface._edit) is True
    assert _focused(widget) is buttons[0]
    assert section.navigate(Qt.Key.Key_Down, buttons[0]) is True
    assert _focused(widget) is buttons[1]
    # A history row is keyboard-activatable (Space → clicked → select), so the
    # stored answer is reachable without a mouse.
    qtbot.keyClick(buttons[1], Qt.Key.Key_Space)
    assert surface.selected_history_index() == 1
    assert surface._result.text() == "answer 1"
    assert section.navigate(Qt.Key.Key_Down, buttons[1]) is True
    assert _focused(widget) is sidebar._close_btn
    assert section.navigate(Qt.Key.Key_Up, sidebar._close_btn) is True
    assert _focused(widget) is buttons[1]

    widget.set_ask_sidebar_visible(False)


def test_flyout_history_is_nav_owned_while_open(qtbot):
    _seed_log(1)
    widget = _widget(qtbot)
    flyout = _open_flyout(qtbot, widget)
    surface = widget._ask_ai_surface

    section = ask_nav.section_of(flyout)
    assert section is not None
    button = surface.history_row_buttons()[0]
    assert section.owns(button) is True
    assert section.owns(surface.question_row) is True

    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)
    assert ask_nav.section_of(flyout) is None


def test_toolbar_ai_toggle_is_owned_by_the_toolbar_section(qtbot):
    """The toggle is a toolbar child, so the toolbar section owns it.

    It is NOT visible: the Ask sidebar is unfinished and the owner hid the
    affordance on 2026-10-27 (pinned by
    ``runtime/test_toolbar_hidden_ask_sidebar.py``). The ownership contract this
    test is about needs the WIDGET, not an offered button — asserting
    visibility here contradicted the owner's decision and left the tier red
    (measured on ``main`` 2026-10-28).
    """
    widget = _widget(qtbot)
    button = widget.toolbar.ask_sidebar_button
    assert button.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert button.isVisible() is False, (
        "the Ask sidebar is unfinished: the button must stay hidden until the "
        "feature is re-exposed (one line in GalleryToolbar)"
    )
    assert button.isVisibleTo(widget.toolbar) is False

    # The gallery tab declares the toolbar container as its first navigation
    # row (``ImageGalleryTab._toolbar_rows``) — so any toolbar child, this
    # toggle included, is section-owned rather than click-only.
    from sli_ui_toolkit.managers import ToolbarRowsSection
    from tabs.image_gallery.tab import ImageGalleryTab

    tab = ImageGalleryTab()
    tab._widget = widget
    assert widget.toolbar in tab._toolbar_rows()

    section = ToolbarRowsSection(lambda: [widget.toolbar], tag="gallery-toolbar-test")
    assert section.owns(button) is True
    # …and the row really walks onto it (Left/Right within the row).
    assert section.navigate(Qt.Key.Key_Right, widget.toolbar.pick_button) is True


# -- i18n -------------------------------------------------------------------


def test_ask_history_and_sidebar_keys_present_in_all_locales():
    base = Path(__file__).resolve().parents[1] / "resources" / "i18n"
    files = sorted(base.glob("*/image_gallery.json"))
    assert len(files) == 4
    keys = ("history_title", "history_empty", "sidebar_show", "sidebar_hide")

    def block(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))["image_gallery"]["ask_ai"]

    en_path = next(path for path in files if path.parent.name == "en")
    english = {key: block(en_path)[key] for key in keys}
    for path in files:
        data = block(path)
        for key in keys:
            assert data.get(key), f"{path}: missing ask_ai.{key}"
        if path == en_path:
            continue
        for key, en_value in english.items():
            assert data[key] != en_value, f"{path}: ask_ai.{key} is still English"
