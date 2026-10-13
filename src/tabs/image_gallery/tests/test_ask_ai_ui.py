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

    # Empty field: Tab accepts the grayed default prompt (submit preset).
    # (Direct handler call: like the old eventFilter-direct test below, a
    # synthetic QTest Tab is not delivered into an in-flyout field.)
    assert flyout._edit.text() == ""
    tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    flyout._edit.keyPressEvent(tab)
    assert tab.isAccepted()
    assert flyout._edit.text() == "Summary"

    # Real Enter path through the preset: resolves and submits field text.
    flyout._edit.setText("custom question")
    enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    flyout._edit.keyPressEvent(enter)
    assert got == ["custom question"]

    flyout.hide()


def test_tab_prefills_default_cursor_at_end_no_selection(qtbot):
    """Tab accepts the prompt with the cursor at the end, NOT selecting it."""
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, scope_label="Selection", default_prompt="What matters here?")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    tab = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    flyout._edit.keyPressEvent(tab)
    assert tab.isAccepted()
    assert flyout._edit.text() == "What matters here?"
    assert flyout._edit.hasSelectedText() is False
    assert flyout._edit.cursorPosition() == len("What matters here?")
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_status_badge_shows_selected_model_not_backend(qtbot):
    """The status badge shows the selected LLM, never the raw 'vlm' backend."""
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, scope_label="Selection", default_prompt="Q")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    flyout.set_texts(model="openai/gpt-4o")

    flyout.show_result("The series is mostly clean.", backend="vlm")

    status = flyout._status.text()
    assert "openai/gpt-4o" in status
    assert "vlm" not in status
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_hide_persists_draft_and_images_toggle(qtbot):
    """Draft text + include-images toggle survive a hide/reopen."""
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, scope_label="Selection", default_prompt="Q")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    flyout._edit.setText("my draft question")
    flyout._images_toggle.setChecked(True)
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)  # fade-out done

    flyout.open_for(anchor, scope_label="Selection", default_prompt="Q")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    assert flyout._edit.text() == "my draft question"
    assert flyout.include_images() is True
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_reopen_uses_saved_user_size_on_first_frame(qtbot):
    """A remembered manual size must apply on the FIRST frame, not after the fade."""
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, scope_label="Selection", default_prompt="Q")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    flyout.apply_user_size(500, 420)
    assert (flyout.width(), flyout.height()) == (500, 420)

    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)

    flyout.open_for(anchor, scope_label="Selection", default_prompt="Q")
    # Immediately (first frame, before any animation settles): saved size.
    assert (flyout.width(), flyout.height()) == (500, 420)
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


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


def test_flyout_minimum_height_tracks_content_layout(qtbot):
    """Min height follows the layout floor, not a fixed constant.

    Pre-fix the floor was a hardcoded 160 scaled px regardless of content, so
    it did not track the layout at all (and the always-present empty rows kept
    the surface tall). The floor must equal what the live layout needs plus the
    shadow margins.
    """
    from sli_ui_toolkit.managers import scaled_px

    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, scope_label="Series 1", default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    layout = flyout.container.layout()
    layout.activate()
    needed = int(layout.minimumSize().height()) + 2 * flyout.SHADOW_RADIUS
    # Empty rows are collapsed, so the live floor is below the old constant —
    # proof it tracks the layout rather than a magic number.
    assert needed < scaled_px(160)
    assert flyout.minimumHeight() == needed
    flyout.hide()


def test_empty_result_and_status_rows_collapse(qtbot):
    """The two bottom labels hide when empty and reappear with content."""
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    qtbot.wait(300)  # past the show fade, when children are restored

    assert not flyout._result.isVisible()
    assert not flyout._status.isVisible()

    flyout.set_busy(True)
    qtbot.wait(50)
    assert flyout._status.isVisible()

    flyout.show_result("an answer", backend="text")
    qtbot.wait(50)
    assert flyout._result.isVisible()
    assert flyout._status.isVisible()

    flyout.show_error("")
    qtbot.wait(50)
    # Error path clears the result pane; an empty status falls back to text,
    # so the result row collapses while the status keeps the message.
    assert not flyout._result.isVisible()
    assert flyout._status.isVisible()
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
    grid._on_series_context_menu = (
        lambda idx, anchor, paths, label, series_id=None, global_pos=None:
        calls.append((idx, tuple(paths), label))
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
            "images_toggle_hint",
            "images_toggle_downsample",
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


def test_ask_ai_images_toggle_defaults_off(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)
    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    assert flyout.findChild(QWidget, "gallery_ask_ai_images_toggle") is not None
    assert flyout.include_images() is False
    flyout.hide()


def test_images_toggle_tooltip_has_two_lines(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)
    flyout = AskAiFlyout(anchor)
    flyout.set_texts(
        images_hint="Send images with the question",
        images_downsample="Downscale: ≤ 768 px",
    )
    assert flyout._images_toggle.toolTip().split("\n") == [
        "Send images with the question",
        "Downscale: ≤ 768 px",
    ]
    flyout.deleteLater()


def test_images_downsample_line_reflects_current_setting():
    from types import SimpleNamespace

    from tabs.image_gallery.controller import GalleryController

    fake = SimpleNamespace(_tr=lambda _key, default: default)
    fmt = GalleryController._images_downsample_text
    assert fmt(fake, 768) == "Downscale: ≤ 768 px"
    assert fmt(fake, 0) == "Original"


def test_ask_ai_images_toggle_persists_across_hide(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)
    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    flyout._images_toggle.setChecked(True)
    flyout._on_images_toggled()
    assert flyout.include_images() is True

    # Persisted across a hide/reopen (not reset) — see hideEvent.
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    assert flyout.include_images() is True
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)
def test_result_image_names_are_accent_links_and_open_quick_look(qtbot):
    """Names in the answer become accent, underlined, selectable links.

    Falsification: pre-change ``show_result`` took no ``links`` and the result
    label was plain/not selectable — this test fails on that build.
    """
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    opened: list[str] = []
    flyout.imageActivated.connect(opened.append)

    flyout.show_result(
        "Prefer Archivist Soft.png; Archivist Rough.png is softer.",
        backend="text",
        links={
            "Archivist Soft.png": "/g/Archivist Soft.png",
            "Archivist Rough.png": "/g/Archivist Rough.png",
        },
    )

    html = flyout._result.text()
    assert '<a href="gallery-image:' in html
    assert "Archivist Soft.png</a>" in html
    assert "text-decoration:underline" in html
    # Selectable text + clickable links coexist on the answer label.
    flags = flyout._result.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    assert flags & Qt.TextInteractionFlag.LinksAccessibleByMouse

    # Activating a link (as a click does) carries the image path out.
    flyout._result.linkActivated.emit("gallery-image:%2Fg%2FArchivist%20Soft.png")
    assert opened == ["/g/Archivist Soft.png"]
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_result_without_links_stays_plain_text(qtbot):
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)
    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, default_prompt="Summary")
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)

    flyout.show_result("2 < 3 & rising", backend="text")
    # PlainText format: the ampersand/angle brackets survive verbatim.
    assert flyout._result.text() == "2 < 3 & rising"
    assert "<a " not in flyout._result.text()
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)


def test_region_flyout_aligns_centered_above_selection(qtbot):
    """grow_up flyouts pin bottom-center to the anchor's top-center.

    Falsification: pre-change grow_up mapped top-left/bottom-left.
    (Pixel placement from those points is toolkit geometry, covered by
    the toolkit's own tests; here we pin the seam contract — the points
    ``open_for`` passes to ``show_aligned``.)
    """
    anchor = QWidget()
    qtbot.addWidget(anchor)
    anchor.resize(200, 100)
    anchor.show()
    qtbot.waitExposed(anchor)

    flyout = AskAiFlyout(anchor)
    qtbot.addWidget(flyout)
    flyout.open_for(anchor, default_prompt="Q", grow_up=True)
    qtbot.waitUntil(lambda: flyout.isVisible(), timeout=5000)
    kwargs = dict(flyout._last_align_kwargs or {})
    assert kwargs.get("anchor_point") == "top-center"
    assert kwargs.get("flyout_point") == "bottom-center"
    flyout.hide()
    qtbot.waitUntil(lambda: not flyout.isVisible(), timeout=5000)

    # The grow-down default is untouched.
    flyout2 = AskAiFlyout(anchor)
    qtbot.addWidget(flyout2)
    flyout2.open_for(anchor, default_prompt="Q")
    qtbot.waitUntil(lambda: flyout2.isVisible(), timeout=5000)
    kwargs2 = dict(flyout2._last_align_kwargs or {})
    assert kwargs2.get("anchor_point") == "bottom-left"
    assert kwargs2.get("flyout_point") == "top-left"
    flyout2.hide()
    qtbot.waitUntil(lambda: not flyout2.isVisible(), timeout=5000)
