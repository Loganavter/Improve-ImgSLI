"""Gate-zone dump: silent without the key, one line with it, never crashes."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import build_gallery_card
from tabs.image_gallery.ui.card.hover import log_card_gates
from core.log_names import APP_LOGGER_NAME


def test_gates_silent_without_key(qtbot, caplog, monkeypatch) -> None:
    from PySide6.QtWidgets import QWidget

    monkeypatch.delenv("IMGSLI_GALLERY_HOVER_DIAG", raising=False)
    parent = QWidget()
    qtbot.addWidget(parent)
    card = build_gallery_card(GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1), parent=parent, owner=None)
    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        log_card_gates(card, None, "enter")
    assert "[gates]" not in caplog.text


def test_gates_dump_with_key_no_crash(qtbot, caplog, monkeypatch) -> None:
    from PySide6.QtWidgets import QWidget

    monkeypatch.setenv("IMGSLI_GALLERY_HOVER_DIAG", "1")
    parent = QWidget()
    qtbot.addWidget(parent)
    owner = SimpleNamespace(state=SimpleNamespace(selected_paths=set()))
    card = build_gallery_card(GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1), parent=parent, owner=owner)
    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        log_card_gates(card, owner, "enter")
    assert "[gates] enter" in caplog.text
    assert "hovered=" in caplog.text and "rejected=" in caplog.text
    # Degenerate inputs must not raise either.
    with caplog.at_level(logging.WARNING, logger=APP_LOGGER_NAME):
        log_card_gates(SimpleNamespace(), None, "sync-hide")


def test_card_tooltip_set_on_build_and_rebind(qtbot) -> None:
    """Hover tooltip shows the full file name, on build and on rebind."""
    from PySide6.QtWidgets import QWidget

    from tabs.image_gallery.ui.card import update_gallery_card

    parent = QWidget()
    qtbot.addWidget(parent)
    card = build_gallery_card(
        GalleryItem(path=Path("/gallery/very_long_filename_01.png"), mtime_ns=1),
        parent=parent, owner=None,
    )
    assert card.toolTip().split("\n")[0] == "very_long_filename_01.png"
    # Pooled rebind to another item must refresh the tooltip, never stale.
    update_gallery_card(
        card, GalleryItem(path=Path("/gallery/other_name_02.png"), mtime_ns=2)
    )
    assert card.toolTip().split("\n")[0] == "other_name_02.png"
