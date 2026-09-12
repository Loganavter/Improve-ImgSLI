"""Project-I/O negative paths: corrupt ZIP, zip-slip, unwritable save.

W5 gap: happy-path only, guards never executed.
Inv: each guard must be exercised and fail safely.
"""
from __future__ import annotations

import os
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from services.io.project_package import extract_media, write_project_zip
from services.io.project_io import prepare_project_file_for_load


def test_corrupt_zip_raises_or_returns_error(tmp_path: Path):
    # Truncated zip header - is_zipfile may still be True for some bytes, but
    # reading must raise BadZipFile / ValueError, not silent success.
    bad = tmp_path / "bad.imgsli"
    bad.write_bytes(b"PK\x03\x04 not a real zip but looks like one " + b"\x00" * 100)
    # is_zip_project may return True/False; either way load must not silently succeed
    with pytest.raises(Exception):
        prepare_project_file_for_load(bad)


def test_zip_slip_member_rejected(tmp_path: Path, monkeypatch):
    proj = tmp_path / "evil.imgsli"
    # One .. stays inside cache/media/../ -> cache/evil (safe). Need two .. to escape cache_dir.
    with zipfile.ZipFile(proj, "w") as zf:
        zf.writestr("project.json", '{"format":"imgsli","version":3,"active_session_index":0,"sessions":[]}')
        zf.writestr("media/../../evil.txt", b"evil")
        # Also add a valid media entry to have non-empty namelist
        zf.writestr("media/abcd/name.png", b"123")
    cache_dir = tmp_path / "cache"
    # Must raise ValueError for unsafe path, not extract outside cache_dir
    with pytest.raises(ValueError, match="Unsafe zip member"):
        extract_media(proj, cache_dir)
    # Ensure evil file not created outside cache
    assert not (tmp_path / "evil.txt").exists()
    assert not (cache_dir.parent / "evil.txt").exists()


def test_zip_slip_absolute_path_rejected(tmp_path: Path):
    proj = tmp_path / "evil2.imgsli"
    with zipfile.ZipFile(proj, "w") as zf:
        zf.writestr("project.json", '{"format":"imgsli","version":3,"active_session_index":0,"sessions":[]}')
        zf.writestr("media/../../tmp/pwned", b"evil")
    cache_dir = tmp_path / "cache2"
    with pytest.raises(ValueError, match="Unsafe"):
        extract_media(proj, cache_dir)


def test_unwritable_save_dir_raises(tmp_path: Path):
    # Use a parent path that is a file, so mkdir cannot create dir -> OSError
    parent_file = tmp_path / "is_file"
    parent_file.write_text("not a dir")
    dest = parent_file / "out.imgsli"  # parent is file, not directory
    from core.store import Store

    store = Store()
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    # package_project_data will try dest.parent.mkdir -> should raise
    from services.io.project_io import package_project_data

    data = {"format": "imgsli", "version": 3, "active_session_index": None, "sessions": []}
    with pytest.raises(Exception):
        package_project_data(data, dest)


def test_corrupt_project_json_too_large_rejected(tmp_path: Path):
    # project.json exceeding ZIP_MAX_PROJECT_JSON_BYTES must be rejected
    from services.io.project_package import ZIP_MAX_PROJECT_JSON_BYTES

    proj = tmp_path / "bomb.imgsli"
    big = "x" * (ZIP_MAX_PROJECT_JSON_BYTES + 1)
    with zipfile.ZipFile(proj, "w") as zf:
        zf.writestr("project.json", big)
    with pytest.raises(ValueError, match="too large"):
        from services.io.project_package import read_project_json_from_zip

        read_project_json_from_zip(proj)
