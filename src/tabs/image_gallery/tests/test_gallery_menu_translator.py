"""Gallery context menus must receive the widget's real translator.

Falsification (pre-fix): both call sites read ``self._gallery_context`` — an
alias that is **never assigned** (the context lives on ``self._context``,
``widget.py:78``) — so ``translate=None`` and the empty-canvas Sort by / View
menu and the card menu rendered English defaults despite having i18n keys.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.widget import ImageGalleryWidget


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(_tr=lambda k, d: f"T[{k}]")


def test_empty_canvas_menu_receives_context_translator(qtbot, monkeypatch) -> None:
    import tabs.image_gallery.ui.card.sort_view_menu as svm

    w = ImageGalleryWidget(context=_ctx())
    qtbot.addWidget(w)
    seen: dict = {}
    monkeypatch.setattr(
        svm, "popup_empty_context_menu",
        lambda *a, **k: seen.setdefault("tr", a[2]),
    )
    w._on_empty_host_context(None)
    assert callable(seen.get("tr")), "empty-canvas menu got translate=None"


def test_card_menu_receives_context_translator(qtbot, monkeypatch) -> None:
    import tabs.image_gallery.ui.card as cardpkg

    w = ImageGalleryWidget(context=_ctx())
    qtbot.addWidget(w)
    w._owner_for_triage = lambda: SimpleNamespace(  # type: ignore[assignment]
        state=SimpleNamespace(selected_paths=set())
    )
    seen: dict = {}
    monkeypatch.setattr(
        cardpkg, "popup_gallery_card_context_menu",
        lambda *a, **k: seen.update(k),
    )
    w._on_card_context(Path("/g/a.png"))
    assert callable(seen.get("translate")), "card menu got translate=None"
