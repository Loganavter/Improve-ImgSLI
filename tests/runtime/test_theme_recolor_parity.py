"""Parity gate over the registered theme-sensitive surfaces.

Each entry is a surface that must visibly recolour across a theme flip. Add a
new surface here when you add one (the static contract catches eager state;
this catches "forgot to repaint / stale cache").
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from services.io.recent_projects import RecentProjectRecord
from tests.helpers.theme_parity import assert_recolors_on_theme_flip

_PANEL = "tabs.session_picker.recent.panel"


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


def _records(tmp_path) -> list[RecentProjectRecord]:
    out = []
    for name, session_type in (("g.imgsli", "image_gallery"), ("c.imgsli", "image_compare")):
        path = tmp_path / name
        path.write_text("{}")
        out.append(
            RecentProjectRecord(
                path=str(path),
                display_name=name,
                opened_at="2026-01-01T00:00:00+00:00",
                session_types=(session_type,),
            )
        )
    return out


def test_recent_shelf_surfaces_recolor_on_theme_flip(qapp, tmp_path, monkeypatch):
    """Regression for inv-theme-recolor-offbyone: chip, cover badge, content fill."""
    import tabs.session_picker.recent.cards as cards_mod

    monkeypatch.setattr(cards_mod, "preview_for_record", lambda _r: None)

    recs = _records(tmp_path)
    monkeypatch.setattr(f"{_PANEL}.list_recent_projects", lambda **k: recs)
    monkeypatch.setattr(f"{_PANEL}.sort_recent_projects", lambda r, **k: list(r))
    monkeypatch.setattr(f"{_PANEL}.get_recent_view_mode", lambda **k: "grid")
    monkeypatch.setattr(f"{_PANEL}.get_recent_sort_mode", lambda **k: "modified")
    monkeypatch.setattr(f"{_PANEL}.get_recent_sort_order", lambda **k: "desc")

    from tabs.session_picker.recent.panel import RecentProjectsPanel

    panel = RecentProjectsPanel(translate=_tr)
    panel.refresh()
    panel.resize(1000, 420)
    panel.show()
    qapp.processEvents()
    try:
        # 1. header chip (was: lagged one theme — synced before chrome recompute)
        assert_recolors_on_theme_flip(qapp, panel._header.sort_button)

        # 2. recent-card cover badge (was: eager QIcon frozen at build)
        card = panel._items.card_for(recs[0].path)
        assert card is not None
        assert_recolors_on_theme_flip(qapp, card)

        # 3. shelf content fill (was: lagged one theme)
        assert_recolors_on_theme_flip(qapp, panel._items.scroll_area.viewport())
    finally:
        panel.deleteLater()
