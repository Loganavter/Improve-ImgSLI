"""Card badge i18n on the UPDATE path + context-dependent menu entries.

Red-before:
- ``update_gallery_card`` never received the tab translator (only the BUILD
  path did), so the SOURCE badge and localized text rows stayed English
  ("SOURCE") on every rebuild / pooled-card rebind.
- The card context menu always offered "Make source" — even for the card that
  already IS the series source (a no-op), i.e. a context-dependent action that
  did not reflect its context.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _tr(key: str, default: str) -> str:
    return "ИСТОЧНИК" if key == "image_gallery.badge.source" else default


def _source_item():
    from tabs.image_gallery.models import GalleryItem

    return GalleryItem(path=Path("/g/a.png"), mtime_ns=1, badge="SOURCE", badge_kind="source")


def _card(qtbot, *, translate=None):
    from tabs.image_gallery.ui.card import build_gallery_card

    kwargs = {"translate": translate} if translate is not None else {}
    card = build_gallery_card(_source_item(), parent=None, **kwargs)
    qtbot.addWidget(card)
    return card


def test_update_gallery_card_localizes_source_badge(qtbot):
    from tabs.image_gallery.ui.card import update_gallery_card

    card = _card(qtbot)
    update_gallery_card(card, _source_item(), translate=_tr)
    assert getattr(card, "_gallery_badge", None) == "ИСТОЧНИК"


def test_update_gallery_card_reuses_build_translator(qtbot):
    """The translator attaches at build — updates need not thread it again."""
    from tabs.image_gallery.ui.card import update_gallery_card

    card = _card(qtbot, translate=_tr)
    update_gallery_card(card, _source_item())  # no translate= on the update
    assert getattr(card, "_gallery_badge", None) == "ИСТОЧНИК"


def test_update_gallery_card_without_translator_keeps_stamp(qtbot):
    """Guard: a missing translator must not crash nor localize."""
    from tabs.image_gallery.ui.card import update_gallery_card

    card = _card(qtbot)
    update_gallery_card(card, _source_item())
    assert getattr(card, "_gallery_badge", None) == "SOURCE"


def test_is_source_reflects_state_source_path():
    from tabs.image_gallery.ui.card.context_menu import _is_source

    owner = SimpleNamespace(state=SimpleNamespace(source_path=Path("/g/a.png")))
    assert _is_source(owner, Path("/g/a.png")) is True
    assert _is_source(owner, Path("/g/b.png")) is False

    owner_none = SimpleNamespace(state=SimpleNamespace(source_path=None))
    assert _is_source(owner_none, Path("/g/a.png")) is False
