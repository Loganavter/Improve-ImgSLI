"""Project preview.png embed / peek helpers (canvas scene grab)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from PySide6.QtGui import QColor, QImage

from services.io.project_package import write_project_zip
from services.io.project_preview import (
    PREVIEW_MEMBER,
    peek_project_preview,
    qimage_to_png_bytes,
    read_preview_image_bytes,
    zip_has_preview,
)


def test_write_project_zip_embeds_preview(tmp_path, qapp):
    img = QImage(32, 18, QImage.Format.Format_RGB32)
    img.fill(QColor(30, 120, 200))
    png = qimage_to_png_bytes(img)
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"

    dest = tmp_path / "demo.imgsli"
    write_project_zip(
        dest,
        {"format": "imgsli", "version": 2, "sessions": []},
        {},
        preview_png=png,
    )
    assert dest.is_file()
    assert zip_has_preview(dest)
    raw = read_preview_image_bytes(dest)
    assert raw == png
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
    png = qimage_to_png_bytes(img)
    dest = tmp_path / "shot.imgsli"
    write_project_zip(
        dest,
        {"format": "imgsli", "version": 2, "sessions": []},
        {},
        preview_png=png,
    )

    pix = peek_project_preview(dest)
    assert pix is not None and not pix.isNull()
    assert list(cache.glob("*.png"))


def test_peek_returns_none_when_member_missing(tmp_path, qapp, monkeypatch):
    cache = tmp_path / "previews"
    cache.mkdir()
    monkeypatch.setattr(
        "services.io.project_preview.project_previews_cache_dir",
        lambda: cache,
    )
    dest = tmp_path / "legacy.imgsli"
    write_project_zip(
        dest,
        {"format": "imgsli", "version": 2, "sessions": []},
        {},
        preview_png=None,
    )
    assert not zip_has_preview(dest)
    assert peek_project_preview(dest) is None


def test_peek_accepts_legacy_preview_jpg(tmp_path, qapp, monkeypatch):
    cache = tmp_path / "previews"
    cache.mkdir()
    monkeypatch.setattr(
        "services.io.project_preview.project_previews_cache_dir",
        lambda: cache,
    )
    img = QImage(24, 16, QImage.Format.Format_RGB32)
    img.fill(QColor(10, 20, 30))
    png = qimage_to_png_bytes(img)
    dest = tmp_path / "old.imgsli"
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr(
            "project.json",
            json.dumps({"format": "imgsli", "version": 2, "sessions": []}),
        )
        zf.writestr("preview.jpg", png)
    assert zip_has_preview(dest)
    pix = peek_project_preview(dest)
    assert pix is not None and not pix.isNull()
