"""Session-picker grid card cover preview (moved out of test_project_preview)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage, QPixmap

from services.io.project_package import write_project_zip
from services.io.project_preview import qimage_to_png_bytes
from services.io.recent_projects import RecentProjectRecord
from tabs.session_picker.recent.cards import _cover_region, build_grid_card


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


def test_grid_card_uses_pixmap_cover(tmp_path, qapp, monkeypatch):
    img = QImage(48, 28, QImage.Format.Format_RGB32)
    img.fill(QColor(10, 180, 90))
    png = qimage_to_png_bytes(img)
    dest = tmp_path / "card.imgsli"
    write_project_zip(
        dest,
        {"format": "imgsli", "version": 2, "sessions": []},
        {},
        preview_png=png,
    )
    monkeypatch.setattr(
        "services.io.project_preview.project_previews_cache_dir",
        lambda: tmp_path / "cache",
    )
    (tmp_path / "cache").mkdir()

    record = RecentProjectRecord(
        path=str(dest),
        display_name="card",
        opened_at="2026-01-01T00:00:00+00:00",
        session_types=("image_compare",),
    )
    region = _cover_region(
        record,
        missing=False,
        corner_radii=(10, 10, 0, 0),
        weight=2.0,
        icon_size_px=28,
    )
    assert region.pixmap is not None
    assert region.image_fill == "cover"

    card = build_grid_card(
        record,
        parent=None,
        tr=_tr,
        on_activate=lambda *_: None,
        on_context_menu=lambda *_: None,
    )
    cover = next(r for r in card.regions() if r.id == "cover")
    assert cover.pixmap is not None
    assert isinstance(cover.pixmap, QPixmap)
    card.deleteLater()