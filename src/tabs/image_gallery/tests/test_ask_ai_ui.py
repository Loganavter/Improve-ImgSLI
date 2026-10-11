"""A3 — Ask AI flyout surface + i18n keys (offscreen).

Covers the plan's A3 verify: default prompt present (Tab accepts it), Enter
submits, the result pane is marked "AI read", and the ask_ai i18n block exists
in all four locales.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from tabs.image_gallery.ui.ask_ai import AskAiFlyout


def test_flyout_tab_accepts_default_and_enter_submits(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    got: list[str] = []
    flyout.submitted.connect(got.append)

    flyout.open_for(anchor, scope_label="Series 1", default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    # Empty field: Tab accepts the grayed default prompt (our eventFilter).
    assert flyout._edit.text() == ""
    tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    assert flyout.eventFilter(flyout._edit, tab) is True
    assert flyout._edit.text() == "Summary"

    # returnPressed sends whatever is in the field (the toolkit edit emits
    # this on Enter; the real key event is exercised live, not here — a
    # synthetic QTest Tab/Return leaves a deferred toolkit action that leaks
    # past teardown into a later theme test).
    flyout._edit.setText("custom question")
    flyout._edit.returnPressed.emit()
    assert got == ["custom question"]

    flyout.hide()


def test_flyout_enter_keypress_event_submits(qtbot):
    """Enter is handled by the flyout itself (no Ask button)."""
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    got: list[str] = []
    flyout.submitted.connect(got.append)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    flyout._edit.setText("via enter")
    event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
    )
    flyout.keyPressEvent(event)
    assert got == ["via enter"]
    flyout.hide()


def test_flyout_result_is_marked_ai_read(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    flyout.show_result("The series is mostly clean.", backend="text")
    assert "AI read" in flyout._status.text()
    assert "clean" in flyout._result.text()

    flyout.show_error("Configure the AI API key in Settings first.")
    assert "Configure" in flyout._status.text()
    flyout.hide()


def test_long_result_wraps_and_grows_flyout(qtbot):
    """A long answer must wrap and grow the flyout, not clip/overlap the status."""
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(300, 200)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, scope_label="Series 1", default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    h0 = flyout.height()

    long = ("All Archivist variants are nearly identical; aggressive "
            "sharpening degraded detail, compression ~1.06%. ") * 4
    flyout.show_result(long, backend="text")
    qtbot.waitUntil(lambda: flyout.height() > h0, timeout=3000)

    assert flyout._result.text().startswith("All Archivist")
    assert flyout._result.height() > flyout._result.fontMetrics().height()
    assert "AI read" in flyout._status.text()
    # The status line sits below the wrapped result, never on top of it.
    assert flyout._result.geometry().bottom() <= flyout._status.geometry().top()
    flyout.hide()


def test_emit_submit_deselects_and_clears_focus(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    got: list[str] = []
    flyout.submitted.connect(got.append)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    flyout._edit.setText("question")
    flyout._edit.setFocus()
    qtbot.waitUntil(lambda: flyout._edit.hasFocus(), timeout=2000)
    flyout._edit.selectAll()
    flyout._emit_submit()

    assert got == ["question"]
    assert flyout._edit.selectedText() == ""
    assert not flyout._edit.hasFocus()
    flyout.hide()


def test_answer_persists_across_hide_and_reopen(qtbot):
    from tabs.image_gallery.services.ask_context import AskScope
    from tabs.image_gallery.services.ask_router import AskResult
    from tabs.image_gallery.widget import ImageGalleryWidget

    widget = ImageGalleryWidget()
    qtbot.addWidget(widget)
    widget.resize(600, 400)
    widget.show()
    qtbot.waitExposed(widget)
    anchor = QWidget()
    qtbot.addWidget(anchor)

    scope = AskScope(kind="selection", paths=(Path("/g/a.png"),), label="Sel")
    widget.open_ask_ai(anchor, scope)
    widget.show_ask_ai_result(AskResult(text="kept answer", backend="text"))
    flyout = widget._ensure_ask_ai_flyout()
    assert "kept answer" in flyout._result.text()

    flyout.hide()
    widget.open_ask_ai(anchor, scope)
    assert "kept answer" in flyout._result.text()
    flyout.hide()


def test_flyout_has_resize_grip_and_min_width(qtbot):
    from sli_ui_toolkit.managers import scaled_px

    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    assert flyout.findChild(QWidget, "gallery_ask_ai_resize_grip") is not None
    assert flyout.minimumWidth() >= scaled_px(300)

    flyout.apply_user_size(560, 260)
    assert flyout.width() == 560
    # Below the minimum clamps up.
    flyout.apply_user_size(40, 40)
    assert flyout.width() >= scaled_px(300)
    flyout.hide()


def test_empty_scope_line_is_hidden(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)

    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    assert flyout._scope.text() == ""
    # Past the fade, the empty scope line stays hidden (fade hides children).
    qtbot.wait(300)
    assert not flyout._scope.isVisible()

    flyout.open_for(anchor, scope_label="Selection", default_prompt="Summary")
    assert flyout._scope.text() == "Selection"
    qtbot.waitUntil(lambda: flyout._scope.isVisible(), timeout=3000)
    flyout.hide()


def test_series_header_context_callback_passes_members_and_label(qtbot):
    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.ui.grid_view import GalleryGridView

    grid = GalleryGridView()
    qtbot.addWidget(grid)
    calls = []
    grid._on_series_context_menu = lambda idx, anchor, paths, label: calls.append(
        (idx, tuple(paths), label)
    )
    item = GalleryItem(path=Path("/g/1.png"), mtime_ns=1)
    grid._series = [[item]]
    grid._series_header_labels = {0: "Series One"}
    anchor = QWidget()
    qtbot.addWidget(anchor)

    grid._handle_series_context(anchor, 0)

    assert calls == [(0, (item.path,), "Series One")]


def test_i18n_ask_ai_keys_present_in_all_locales():
    base = Path(__file__).resolve().parents[1] / "resources" / "i18n"
    files = sorted(base.glob("*/image_gallery.json"))
    assert len(files) == 4
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        block = data["image_gallery"]["ask_ai"]
        for key in (
            "action",
            "title",
            "default_prompt",
            "busy",
            "read_badge",
            "error",
            "routing_unavailable",
        ):
            assert block.get(key), f"{path}: missing ask_ai.{key}"


def test_flyout_chrome_is_localizable(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.set_texts(
        title="Спросить у ИИ",
        busy="Думаю…",
        read_badge="Ответ ИИ, не проверено",
        error="ИИ не смог ответить.",
    )
    flyout.open_for(anchor, default_prompt="Сводка")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    assert flyout._title.text() == "Спросить у ИИ"

    flyout.set_busy(True)
    assert flyout._status.text() == "Думаю…"
    flyout.set_busy(False)
    flyout.show_result("готово", backend="text")
    assert "Ответ ИИ" in flyout._status.text()
    flyout.hide()
