from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.services.folder_scanner import scan_folder


def test_scan_folder_filters_by_extension_and_is_flat(tmp_path: Path):
    (tmp_path / "b.png").write_bytes(b"\x00")
    (tmp_path / "a.jpg").write_bytes(b"\x00")
    (tmp_path / "notes.txt").write_text("hello")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.png").write_bytes(b"\x00")

    items = scan_folder(tmp_path)
    names = [item.name for item in items]

    assert names == ["a.jpg", "b.png"]


def test_scan_folder_missing_dir_returns_empty(tmp_path: Path):
    assert scan_folder(tmp_path / "does_not_exist") == []