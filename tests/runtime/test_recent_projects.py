"""MRU recent projects store."""

from __future__ import annotations

import os

import pytest
from PySide6.QtCore import QSettings

from services.io import recent_projects as rp
from services.io.recent_projects import (
    SORT_ASC,
    SORT_CREATED,
    SORT_DATE,
    SORT_DESC,
    SORT_MODIFIED,
    SORT_NAME,
    VIEW_GRID,
    VIEW_LIST,
    get_recent_sort_mode,
    get_recent_sort_order,
    get_recent_view_mode,
    list_recent_projects,
    normalize_recent_sort_mode,
    record_recent_project,
    remove_recent_project,
    set_recent_sort_mode,
    set_recent_sort_order,
    set_recent_view_mode,
    sort_recent_projects,
)


@pytest.fixture
def qs(tmp_path, monkeypatch):
    ini = tmp_path / "recent.ini"
    settings = QSettings(str(ini), QSettings.Format.IniFormat)
    return settings


def test_record_dedupes_and_caps(qs, tmp_path):
    paths = []
    for i in range(20):
        p = tmp_path / f"proj_{i}.imgsli"
        p.write_bytes(b"PK\x03\x04")  # not a real zip; peek fails → empty types
        paths.append(p)
        result = record_recent_project(
            p, session_types=("image_compare",), settings=qs, cap=16
        )
        assert result.record.display_name == f"proj_{i}"
        if i >= 16:
            assert result.evicted is not None

    records = list_recent_projects(settings=qs)
    assert len(records) == 16
    assert records[0].display_name == "proj_19"
    assert records[0].session_types == ("image_compare",)

    # Re-open an older entry that is still in the capped list → moves to front.
    still_in_list = records[-1].path
    result = record_recent_project(
        still_in_list, session_types=("multi_compare",), settings=qs, cap=16
    )
    assert result.evicted is None  # already in list; no growth past cap
    records = list_recent_projects(settings=qs)
    assert len(records) == 16
    assert records[0].path == still_in_list
    assert records[0].session_types == ("multi_compare",)


def test_record_reports_evicted_oldest_at_cap(qs, tmp_path):
    from services.io.recent_projects import (
        DEFAULT_CAP,
        format_recent_cap_eviction_message,
    )

    assert DEFAULT_CAP == 1000
    for i in range(2):
        p = tmp_path / f"cap_{i}.imgsli"
        p.write_text("{}")
        result = record_recent_project(p, settings=qs, cap=2)
        assert result.evicted is None

    newest = tmp_path / "cap_new.imgsli"
    newest.write_text("{}")
    result = record_recent_project(newest, settings=qs, cap=2)
    assert result.evicted is not None
    assert result.evicted.display_name == "cap_0"
    message = format_recent_cap_eviction_message(result.evicted, cap=2)
    assert "cap_0" in message
    assert "2" in message
    assert "github.com" in message


def test_remove_recent_project(qs, tmp_path):
    a = tmp_path / "a.imgsli"
    b = tmp_path / "b.imgsli"
    a.write_text("{}")
    b.write_text("{}")
    record_recent_project(a, settings=qs)
    record_recent_project(b, settings=qs)
    assert remove_recent_project(a, settings=qs) is True
    records = list_recent_projects(settings=qs)
    assert [r.display_name for r in records] == ["b"]
    assert remove_recent_project(a, settings=qs) is False


def test_sort_by_modified_created_and_name(qs, tmp_path, monkeypatch):
    older = tmp_path / "zeta.imgsli"
    newer = tmp_path / "alpha.imgsli"
    older.write_text("{}")
    newer.write_text("{}")
    record_recent_project(older, settings=qs)
    record_recent_project(newer, settings=qs)

    older_path = str(older.resolve())
    newer_path = str(newer.resolve())
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))

    records = list_recent_projects(settings=qs)
    by_mtime = sort_recent_projects(records, sort_by=SORT_MODIFIED)
    assert by_mtime[0].display_name == "alpha"
    by_mtime_asc = sort_recent_projects(
        records, sort_by=SORT_MODIFIED, sort_order=SORT_ASC
    )
    assert by_mtime_asc[0].display_name == "zeta"

    # Creation order can be inverted vs mtime; stub the key helpers.
    created = {older_path: 200.0, newer_path: 100.0}
    monkeypatch.setattr(rp, "_path_created", lambda p: created.get(p, 0.0))
    by_created = sort_recent_projects(records, sort_by=SORT_CREATED)
    assert by_created[0].display_name == "zeta"

    by_name = sort_recent_projects(
        records, sort_by=SORT_NAME, sort_order=SORT_ASC
    )
    assert [r.display_name for r in by_name] == ["alpha", "zeta"]
    by_name_desc = sort_recent_projects(
        records, sort_by=SORT_NAME, sort_order=SORT_DESC
    )
    assert [r.display_name for r in by_name_desc] == ["zeta", "alpha"]


def test_view_and_sort_prefs(qs):
    set_recent_view_mode(VIEW_LIST, settings=qs)
    set_recent_sort_mode(SORT_NAME, settings=qs)
    set_recent_sort_order(SORT_ASC, settings=qs)
    assert get_recent_view_mode(settings=qs) == VIEW_LIST
    assert get_recent_sort_mode(settings=qs) == SORT_NAME
    assert get_recent_sort_order(settings=qs) == SORT_ASC
    set_recent_view_mode(VIEW_GRID, settings=qs)
    set_recent_sort_mode(SORT_MODIFIED, settings=qs)
    set_recent_sort_order(SORT_DESC, settings=qs)
    assert get_recent_view_mode(settings=qs) == VIEW_GRID
    assert get_recent_sort_mode(settings=qs) == SORT_MODIFIED
    assert get_recent_sort_order(settings=qs) == SORT_DESC
    set_recent_sort_mode(SORT_CREATED, settings=qs)
    assert get_recent_sort_mode(settings=qs) == SORT_CREATED
    # Legacy prefs value ``date`` still resolves to modification time.
    qs.setValue("session_picker.recent.sort", "date")
    assert get_recent_sort_mode(settings=qs) == SORT_MODIFIED
    assert normalize_recent_sort_mode("date") == SORT_DATE == SORT_MODIFIED


def test_drop_missing(qs, tmp_path):
    alive = tmp_path / "alive.imgsli"
    dead = tmp_path / "dead.imgsli"
    alive.write_text("{}")
    dead.write_text("{}")
    record_recent_project(dead, settings=qs)
    record_recent_project(alive, settings=qs)
    dead.unlink()
    kept = list_recent_projects(settings=qs, drop_missing=True)
    assert [r.display_name for r in kept] == ["alive"]


def test_pinned_at_preserved_on_reopen(qs, tmp_path, monkeypatch):
    project = tmp_path / "keep.imgsli"
    project.write_text("{}")
    first = record_recent_project(project, settings=qs).record
    assert first.pinned_at
    assert first.pinned_at == first.opened_at
    pinned = first.pinned_at

    # Force a distinct "now" on re-open so opened_at advances.
    from services.io import recent_projects as rp_mod

    monkeypatch.setattr(rp_mod, "_now_iso", lambda: "2099-01-01T00:00:00+00:00")
    second = record_recent_project(
        project, session_types=("multi_compare",), settings=qs
    ).record
    assert second.pinned_at == pinned
    assert second.opened_at == "2099-01-01T00:00:00+00:00"
    assert second.session_types == ("multi_compare",)
    records = list_recent_projects(settings=qs)
    assert records[0].pinned_at == pinned
    assert records[0].opened_at == "2099-01-01T00:00:00+00:00"


def test_legacy_record_falls_back_pinned_at_to_opened(qs):
    from services.io.recent_projects import RecentProjectRecord

    record = RecentProjectRecord.from_dict(
        {
            "path": "/tmp/legacy.imgsli",
            "display_name": "legacy",
            "opened_at": "2024-06-01T12:00:00+00:00",
            "session_types": ["image_compare"],
        }
    )
    assert record is not None
    assert record.pinned_at == "2024-06-01T12:00:00+00:00"
    assert "pinned_at" in record.to_dict()
    assert record.file_modified_at == ""
    assert record.file_created_at == ""


def test_record_snapshots_file_times_and_keeps_them_when_missing(qs, tmp_path):
    project = tmp_path / "timed.imgsli"
    project.write_text("{}")
    recorded = record_recent_project(
        project, session_types=("image_compare",), settings=qs
    ).record
    assert recorded.file_modified_at
    assert recorded.file_created_at
    assert recorded.session_types == ("image_compare",)
    modified = recorded.file_modified_at
    created = recorded.file_created_at

    project.unlink()
    # Re-writing settings via list still retains times on the stored record.
    records = list_recent_projects(settings=qs, drop_missing=False)
    assert len(records) == 1
    assert records[0].file_modified_at == modified
    assert records[0].file_created_at == created
    assert records[0].session_types == ("image_compare",)

    by_mtime = sort_recent_projects(records, sort_by=SORT_MODIFIED)
    by_created = sort_recent_projects(records, sort_by=SORT_CREATED)
    assert by_mtime[0].path == records[0].path
    assert by_created[0].path == records[0].path
