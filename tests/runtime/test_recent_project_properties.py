"""Recent project Properties action reuses Image Properties dialog."""

from __future__ import annotations

from plugins.image_properties.service import build_image_properties
from services.io.recent_projects import RecentProjectRecord
from tabs.session_picker.recent.relative_time import format_absolute_timestamp


def _tr(key: str, default: str | None = None) -> str:
    return default if default is not None else key


def test_format_absolute_timestamp_localizes():
    text = format_absolute_timestamp("2026-01-01T12:30:00+00:00")
    assert text.startswith("2026-01-01")
    assert len(text) >= 19


def test_missing_record_properties_include_cached_fields(tmp_path):
    record = RecentProjectRecord(
        path=str(tmp_path / "gone.imgsli"),
        display_name="My Project",
        opened_at="2026-02-01T10:00:00+00:00",
        pinned_at="2025-11-15T08:00:00+00:00",
        file_modified_at="2026-01-20T14:00:00+00:00",
        file_created_at="2025-10-01T09:00:00+00:00",
        session_types=("image_compare",),
    )
    props = build_image_properties(
        path=record.path,
        display_name=record.display_name,
        probe_image=False,
        app_rows=(
            ("recent.prop_status", "Status", _tr("recent.missing", "File missing")),
            (
                "recent.prop_file_modified",
                "Date modified",
                format_absolute_timestamp(record.file_modified_at),
            ),
            (
                "recent.prop_file_created",
                "Date created",
                format_absolute_timestamp(record.file_created_at),
            ),
            (
                "recent.prop_pinned",
                "Added to Recent",
                format_absolute_timestamp(record.pinned_at),
            ),
            (
                "recent.prop_opened",
                "Last opened",
                format_absolute_timestamp(record.opened_at),
            ),
            ("recent.prop_sessions", "Sessions", "Image Compare"),
        ),
    )
    assert props.title == "My Project"
    file_section = props.sections[0]
    names = {row.fallback_label: row.value for row in file_section.rows}
    assert names["Name"] == "My Project"
    assert str(tmp_path / "gone.imgsli") in names["Path"]

    app_section = next(s for s in props.sections if s.fallback_title == "In app")
    app_values = {row.fallback_label: row.value for row in app_section.rows}
    assert app_values["Status"] == "File missing"
    assert "2026-01-20" in app_values["Date modified"]
    assert "2025-10-01" in app_values["Date created"]
    assert "2025-11-15" in app_values["Added to Recent"]
    assert "2026-02-01" in app_values["Last opened"]
    assert app_values["Sessions"] == "Image Compare"
