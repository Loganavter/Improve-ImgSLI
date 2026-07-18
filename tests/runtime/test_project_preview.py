"""Project preview.jpg embed / peek helpers."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPixmap

from services.io.project_package import write_project_zip
from services.io.project_preview import (
    PREVIEW_MEMBER,
    peek_project_preview,
    qimage_to_jpeg_bytes,
    read_preview_jpeg_bytes,
    zip_has_preview,
)
from services.io.recent_projects import RecentProjectRecord
from tabs.session_picker.recent.cards import _cover_region, build_grid_card


def _tr(key: str, default: str = "", *args, **kwargs) -> str:
    return default or key


def test_write_project_zip_embeds_preview(tmp_path, qapp):
    img = QImage(32, 18, QImage.Format.Format_RGB32)
    img.fill(QColor(30, 120, 200))
    jpeg = qimage_to_jpeg_bytes(img)
    assert jpeg

    dest = tmp_path / "demo.imgsli"
    write_project_zip(
        dest,
        {"format": "imgsli", "version": 2, "sessions": []},
        {},
        preview_jpeg=jpeg,
    )
    assert dest.is_file()
    assert zip_has_preview(dest)
    raw = read_preview_jpeg_bytes(dest)
    assert raw == jpeg
    with zipfile.ZipFile(dest, "r") as zf:
        assert PREVIEW_MEMBER in zf.namelist()
        assert "project.json" in zf.namelist()
        data = json.loads(zf.read("project.json"))
        assert data["format"] == "imgsli"


def test_peek_project_preview_loads_pixmap(tmp_path, qapp, monkeypatch):
    cache = tmp_path / "previews"
    cache.mkdir()
    monkeypatch.setattr(
        "services.io.project_preview.project_previews_cache_dir",
        lambda: cache,
    )

    img = QImage(40, 24, QImage.Format.Format_RGB32)
    img.fill(QColor(200, 40, 40))
    jpeg = qimage_to_jpeg_bytes(img)
    dest = tmp_path / "shot.imgsli"
    write_project_zip(
        dest,
        {"format": "imgsli", "version": 2, "sessions": []},
        {},
        preview_jpeg=jpeg,
    )

    pix = peek_project_preview(dest)
    assert pix is not None and not pix.isNull()
    assert list(cache.glob("*.jpg"))


def test_grid_card_uses_pixmap_cover(tmp_path, qapp, monkeypatch):
    img = QImage(48, 28, QImage.Format.Format_RGB32)
    img.fill(QColor(10, 180, 90))
    jpeg = qimage_to_jpeg_bytes(img)
    dest = tmp_path / "card.imgsli"
    write_project_zip(
        dest,
        {"format": "imgsli", "version": 2, "sessions": []},
        {},
        preview_jpeg=jpeg,
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

    # Cover/preview is grid-only.
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


def test_canvas_from_page_finds_nested_multi_compare_canvas(qapp):
    """Multi Compare wraps the host; preview must still find ``.canvas``."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from services.io.project_preview import _canvas_from_page

    class _FakeCanvas(QWidget):
        def grabFramebuffer(self):
            img = QImage(8, 8, QImage.Format.Format_RGB32)
            img.fill(QColor(1, 2, 3))
            return img

    class _FakeMultiHost(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.canvas = _FakeCanvas(self)

    outer = QWidget()
    layout = QVBoxLayout(outer)
    host = _FakeMultiHost(outer)
    layout.addWidget(host)

    assert getattr(outer, "canvas", None) is None
    assert _canvas_from_page(outer) is host.canvas

    ic_page = QWidget()
    ic_page.image_label = _FakeCanvas(ic_page)
    assert _canvas_from_page(ic_page) is ic_page.image_label

    outer.deleteLater()
    ic_page.deleteLater()
