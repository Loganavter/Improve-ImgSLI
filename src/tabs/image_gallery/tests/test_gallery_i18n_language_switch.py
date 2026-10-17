"""Live language switch + declarative-key localization for the gallery.

Three falsification stories (all fail on the base):

1. ``toolbar.retranslate()`` / ``stats_strip.retranslate()`` existed but were
   never called, so a language switch left stale English chrome.
2. The card context menu was built from pre-resolved ``_t(translate, …)``
   strings; with no ``translate=`` threaded it rendered English. Now the
   standard entries carry a ``text_key`` and the menu resolves the page
   translator bound by ``install_translator`` (no ``translate=`` needed).
3. The Quick Look size notes (``mixed sizes`` / ``upscale ×N …``) were
   hardcoded English literals regardless of the active language.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.i18n import emit_language_changed, install_translator

from tabs.image_gallery.widget import ImageGalleryWidget

_KEEP_ALIVE: list[QWidget] = []


def _ctx():
    """Fake TabContext whose ``_tr`` is language-live via the toolkit bus."""

    def _tr(key, default=None):
        from sli_ui_toolkit.i18n import get_current_language

        return f"{get_current_language()}[{key}]"

    return SimpleNamespace(_tr=_tr)


def _btn_text(btn) -> str:
    try:
        text = getattr(btn, "_text", "") or ""
        if text:
            return text
    except Exception:
        pass
    try:
        for region in btn.regions():
            text = getattr(region, "text", "") or ""
            if text:
                return text
            for row in getattr(region, "rows", None) or []:
                text = getattr(row, "text", "") or ""
                if text:
                    return text
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# 1. Language switch re-renders toolbar + stats chrome
# ---------------------------------------------------------------------------


def test_language_switch_updates_toolbar_and_stats(qtbot) -> None:
    w = ImageGalleryWidget(context=_ctx())
    qtbot.addWidget(w)
    try:
        emit_language_changed("ru")
        assert _btn_text(w.toolbar._pick_button) == "ru[image_gallery.toolbar.open_folder]"
        assert _btn_text(w.stats_strip._compare_btn) == (
            "ru[image_gallery.stats.compare_finalists]"
        )

        emit_language_changed("en")
        assert _btn_text(w.toolbar._pick_button) == "en[image_gallery.toolbar.open_folder]"
        assert _btn_text(w.stats_strip._compare_btn) == (
            "en[image_gallery.stats.compare_finalists]"
        )
    finally:
        emit_language_changed("en")


def test_install_translator_does_not_corrupt_widget_translators(qtbot) -> None:
    """The toolkit fan-out calls ``retranslate(lang)``; a str must not
    overwrite the callable toolbar/stats translator (would freeze English)."""
    ctx = _ctx()
    w = ImageGalleryWidget(context=ctx)
    qtbot.addWidget(w)
    try:
        assert w.toolbar._tr is ctx._tr
        assert w.stats_strip._tr is ctx._tr
    finally:
        emit_language_changed("en")


# ---------------------------------------------------------------------------
# 2. Card context menu localizes without a threaded translate=
# ---------------------------------------------------------------------------


def test_card_context_menu_localizes_without_translate(qtbot, monkeypatch) -> None:
    from sli_ui_toolkit.widgets import ContextMenu

    import ui.context_menu.manager as _mgr
    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    page = QWidget()
    qtbot.addWidget(page)
    _KEEP_ALIVE.append(page)
    install_translator(page, _ctx()._tr)
    card = QWidget(page)

    captured: dict = {}

    def _fake_open(*, source_widget, global_pos, entries, key, on_triggered=None, **_kwargs):
        # Real menu (the builder binds the resolved translator to it), just
        # without the popup-surface show the manager would perform.
        menu = ContextMenu(source_widget, entries=entries, on_triggered=on_triggered)
        captured["menu"] = menu
        return menu

    monkeypatch.setattr(_mgr, "open_context_menu_entries", _fake_open)

    owner = SimpleNamespace(state=SimpleNamespace(selected_paths=set()))
    emit_language_changed("ru")
    try:
        popup_gallery_card_context_menu(
            card, owner, Path("/g/a.png"), global_pos=None, selection_count=0
        )
        menu = captured.get("menu")
        assert menu is not None
        row = menu.row_for_action("gallery.make_best")
        assert row is not None
        assert row._text == "ru[image_gallery.card.make_best]"
    finally:
        emit_language_changed("en")


def test_open_card_menu_keeps_its_labels_until_reopened(qtbot) -> None:
    """A language switch does NOT relayout the already-open card menu.

    Accepted limitation (``card-menu-collapse``, 2026-10-17): the card menu
    localizes when its entries are built, exactly like every other context
    menu. Switching the language while it is open leaves its labels as they
    were; the NEXT open uses the new language. Relabelling the open menu
    required binding a translator to the shown popup, and that ``retranslate``
    -> ``_relayout_widths`` -> ``adjustSize`` ran while the show-time fade hid
    the menu's container, collapsing it to a sliver.

    Falsification: on the pre-fix code the bind subscribes the menu to the
    language bus, so the emit below changes ``row._text`` and this assertion
    fails.
    """
    from ui.context_menu.manager import get_context_menu_manager

    from tabs.image_gallery.models import GalleryItem
    from tabs.image_gallery.ui.card.context_menu import popup_gallery_card_context_menu

    # The page lives INSIDE a window: the manager parents the menu to the
    # window (``card.window()``), so the shown menu is outside the page's
    # ``install_translator`` subtree — exactly the app layout. Installing the
    # translator on the top-level would auto-cover the menu and hide the
    # mechanism this test pins.
    window = QWidget()
    qtbot.addWidget(window)
    _KEEP_ALIVE.append(window)
    window.resize(900, 600)
    window.show()
    w = ImageGalleryWidget(window)
    w.resize(900, 600)
    w.show()
    install_translator(w, _ctx()._tr)
    items = [
        GalleryItem(path=Path(f"/g/{i}.png"), mtime_ns=1, series_id="s", rank=i)
        for i in range(3)
    ]
    w._grid_view.rebuild_grid(items)
    qtbot.wait(10)

    card = w._grid_view.card_for(items[0].path)
    assert card is not None

    emit_language_changed("ru")
    try:
        popup_gallery_card_context_menu(
            card, w, items[0].path, global_pos=QPoint(300, 200), selection_count=0
        )
        manager = get_context_menu_manager()
        menu = manager._active_menu
        assert menu is not None, "card menu was not opened"
        row = menu.row_for_action("gallery.make_best")
        assert row is not None
        before = row._text
        assert before.startswith("ru["), before

        emit_language_changed("pt_BR")
        qtbot.wait(30)
        assert row._text == before, (
            "the OPEN card menu was relayout-ed by a language switch; "
            "that is the card-menu-collapse mechanism"
        )

        menu.hide()
        popup_gallery_card_context_menu(
            card, w, items[0].path, global_pos=QPoint(300, 200), selection_count=0
        )
        menu2 = manager._active_menu
        assert menu2 is not None, "card menu did not reopen"
        row2 = menu2.row_for_action("gallery.make_best")
        assert row2 is not None and row2._text.startswith("pt_BR["), (
            f"the next open did not localize into the new language: {row2 and row2._text!r}"
        )
        menu2.hide()
    finally:
        emit_language_changed("en")


# ---------------------------------------------------------------------------
# 3. Quick Look size notes follow the language
# ---------------------------------------------------------------------------


def _item(path, w, h):
    return SimpleNamespace(path=path, name=Path(path).name, metrics={"width": w, "height": h})


def test_ql_mixed_sizes_note_localizes() -> None:
    from tabs.image_gallery.ui.quick_look.headers import series_size_note

    ov = SimpleNamespace(
        _series_items=[_item("/g/a.jpg", 100, 100), _item("/g/b.jpg", 200, 100)],
        _source_path=None,
        _tr=lambda k, d: f"A[{k}]",
    )
    assert series_size_note(ov) == "A[image_gallery.quick_look.mixed_sizes]"
    ov._tr = lambda k, d: f"B[{k}]"
    assert series_size_note(ov) == "B[image_gallery.quick_look.mixed_sizes]"


def test_ql_meta_upscale_localizes(qtbot) -> None:
    from tabs.image_gallery.ui.quick_look.meta import populate_filename_meta

    meta = SimpleNamespace(text="")

    def _set_text(text):
        meta.text = text

    ov = SimpleNamespace(
        _filename_label=SimpleNamespace(setText=lambda t: None),
        _meta_label=SimpleNamespace(setText=_set_text),
        _source_path="/g/src.jpg",
        _series_items=[],
        _owner=None,
        _tr=lambda k, d: f"A[{d}]",
    )
    item = SimpleNamespace(
        path="/g/a.jpg",
        name="a.jpg",
        metrics={"width": 200, "height": 200, "upscale_factor": 4},
    )
    populate_filename_meta(ov, item, True, owner=None)
    assert "A[upscale ×4 from source]" in meta.text

    ov._tr = lambda k, d: f"B[{d}]"
    populate_filename_meta(ov, item, True, owner=None)
    assert "B[upscale ×4 from source]" in meta.text
