"""MRU list of portable ``.imgsli`` projects for the Session Picker."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

logger = logging.getLogger("ImproveImgSLI")

_SETTINGS_ORG = "improve-imgsli"
_SETTINGS_APP = "improve-imgsli"
_SETTINGS_KEY = "recent_projects"
_VIEW_KEY = "session_picker.recent.view"
_SORT_KEY = "session_picker.recent.sort"
_SORT_ORDER_KEY = "session_picker.recent.sort_order"
DEFAULT_CAP = 16

VIEW_GRID = "grid"
VIEW_LIST = "list"
SORT_MODIFIED = "modified"
SORT_CREATED = "created"
SORT_NAME = "name"
# Legacy prefs value ``"date"`` mapped to modification time.
SORT_DATE = SORT_MODIFIED
SORT_ASC = "asc"
SORT_DESC = "desc"


@dataclass(frozen=True)
class RecentProjectRecord:
    path: str
    display_name: str
    opened_at: str
    # When the card was first pinned to Recent (survives re-open / missing path).
    pinned_at: str = ""
    # Last known on-disk times (ISO), refreshed whenever the project is recorded.
    file_modified_at: str = ""
    file_created_at: str = ""
    session_types: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "display_name": self.display_name,
            "opened_at": self.opened_at,
            "pinned_at": self.pinned_at or self.opened_at,
            "file_modified_at": self.file_modified_at,
            "file_created_at": self.file_created_at,
            "session_types": list(self.session_types),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecentProjectRecord | None:
        path = str(data.get("path") or "").strip()
        if not path:
            return None
        display = str(data.get("display_name") or "").strip() or Path(path).stem
        opened = str(data.get("opened_at") or "").strip() or _now_iso()
        pinned = str(data.get("pinned_at") or "").strip() or opened
        modified = str(data.get("file_modified_at") or "").strip()
        created = str(data.get("file_created_at") or "").strip()
        types_raw = data.get("session_types") or ()
        types: list[str] = []
        if isinstance(types_raw, (list, tuple)):
            for item in types_raw:
                text = str(item or "").strip()
                if text and text not in types:
                    types.append(text)
        return cls(
            path=path,
            display_name=display,
            opened_at=opened,
            pinned_at=pinned,
            file_modified_at=modified,
            file_created_at=created,
            session_types=tuple(types),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _settings():
    from PySide6.QtCore import QSettings

    return QSettings(_SETTINGS_ORG, _SETTINGS_APP)


def _normalize_path(path: str | Path) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except OSError:
        return str(Path(path).expanduser())


def peek_session_types(path: str | Path) -> tuple[str, ...]:
    """Read session_type list from ``project.json`` without extracting media."""
    project_path = Path(path)
    try:
        from services.io.project_package import (
            is_zip_project,
            read_project_json_from_zip,
        )

        if is_zip_project(project_path):
            data = read_project_json_from_zip(project_path)
        else:
            data = json.loads(project_path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("peek_session_types failed for %s", path, exc_info=True)
        return ()

    types: list[str] = []
    for entry in data.get("sessions") or []:
        if not isinstance(entry, dict):
            continue
        st = str(entry.get("session_type") or "").strip()
        if st and st != "session_picker" and st not in types:
            types.append(st)
    return tuple(types)


def list_recent_projects(
    *,
    settings=None,
    drop_missing: bool = False,
) -> list[RecentProjectRecord]:
    qs = settings if settings is not None else _settings()
    raw = qs.value(_SETTINGS_KEY, "")
    records = _parse_records(raw)
    if not drop_missing:
        return records
    kept: list[RecentProjectRecord] = []
    changed = False
    for record in records:
        if Path(record.path).is_file():
            kept.append(record)
        else:
            changed = True
    if changed:
        _write_records(qs, kept)
    return kept


def _epoch_to_iso(epoch: float) -> str:
    try:
        return (
            datetime.fromtimestamp(float(epoch), tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        )
    except (OSError, OverflowError, ValueError):
        return ""


def _snapshot_file_times(path: str | Path) -> tuple[str, str]:
    """Return ``(file_modified_at, file_created_at)`` ISO strings, or empty."""
    try:
        st = Path(path).stat()
        modified = _epoch_to_iso(float(st.st_mtime))
        birth = getattr(st, "st_birthtime", None)
        created_epoch = float(birth) if birth is not None else float(st.st_ctime)
        created = _epoch_to_iso(created_epoch)
        return modified, created
    except OSError:
        return "", ""


def record_recent_project(
    path: str | Path,
    *,
    session_types: Sequence[str] | None = None,
    settings=None,
    cap: int = DEFAULT_CAP,
) -> RecentProjectRecord:
    qs = settings if settings is not None else _settings()
    normalized = _normalize_path(path)
    display_name = Path(normalized).stem or "Untitled"

    existing_all = list_recent_projects(settings=qs)
    prior = next(
        (r for r in existing_all if _normalize_path(r.path) == normalized),
        None,
    )

    types: tuple[str, ...]
    if session_types is not None:
        types = tuple(
            t for t in (str(x).strip() for x in session_types) if t and t != "session_picker"
        )
    else:
        types = peek_session_types(normalized)
        if not types and prior is not None:
            types = prior.session_types

    now = _now_iso()
    pinned_at = (
        (prior.pinned_at or prior.opened_at) if prior is not None else now
    )
    modified_at, created_at = _snapshot_file_times(normalized)
    if not modified_at and prior is not None:
        modified_at = prior.file_modified_at
    if not created_at and prior is not None:
        created_at = prior.file_created_at

    new_record = RecentProjectRecord(
        path=normalized,
        display_name=display_name,
        opened_at=now,
        pinned_at=pinned_at,
        file_modified_at=modified_at,
        file_created_at=created_at,
        session_types=types,
    )
    existing = [r for r in existing_all if _normalize_path(r.path) != normalized]
    updated = [new_record, *existing][: max(1, int(cap))]
    _write_records(qs, updated)
    return new_record

def remove_recent_project(path: str | Path, *, settings=None) -> bool:
    qs = settings if settings is not None else _settings()
    normalized = _normalize_path(path)
    records = list_recent_projects(settings=qs)
    kept = [r for r in records if _normalize_path(r.path) != normalized]
    if len(kept) == len(records):
        return False
    _write_records(qs, kept)
    return True


def _path_mtime(path: str) -> float:
    try:
        return float(Path(path).stat().st_mtime)
    except OSError:
        return 0.0


def _path_created(path: str) -> float:
    """Best-effort creation time (birthtime when available, else ``st_ctime``)."""
    try:
        st = Path(path).stat()
        birth = getattr(st, "st_birthtime", None)
        if birth is not None:
            return float(birth)
        return float(st.st_ctime)
    except OSError:
        return 0.0


def _iso_to_epoch(value: str) -> float:
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(dt.timestamp())
    except Exception:
        return 0.0


def _record_created_key(record: RecentProjectRecord) -> float:
    created = _path_created(record.path)
    if created > 0.0:
        return created
    return _iso_to_epoch(
        record.file_created_at or record.pinned_at or record.opened_at
    )


def _record_modified_key(record: RecentProjectRecord) -> float:
    modified = _path_mtime(record.path)
    if modified > 0.0:
        return modified
    return _iso_to_epoch(record.file_modified_at or record.opened_at)


def normalize_recent_sort_mode(mode: str | None) -> str:
    value = str(mode or "").strip().lower()
    if value == SORT_NAME:
        return SORT_NAME
    if value == SORT_CREATED:
        return SORT_CREATED
    # ``date`` (legacy) and ``modified`` both mean file modification time.
    return SORT_MODIFIED


def sort_recent_projects(
    records: Iterable[RecentProjectRecord],
    *,
    sort_by: str = SORT_MODIFIED,
    sort_order: str = SORT_DESC,
) -> list[RecentProjectRecord]:
    items = list(records)
    reverse = str(sort_order).strip().lower() != SORT_ASC
    mode = normalize_recent_sort_mode(sort_by)
    if mode == SORT_NAME:
        return sorted(items, key=lambda r: r.display_name.casefold(), reverse=reverse)
    if mode == SORT_CREATED:
        return sorted(items, key=_record_created_key, reverse=reverse)
    return sorted(items, key=_record_modified_key, reverse=reverse)


def get_recent_view_mode(*, settings=None) -> str:
    qs = settings if settings is not None else _settings()
    value = str(qs.value(_VIEW_KEY, VIEW_GRID) or VIEW_GRID).strip().lower()
    return VIEW_LIST if value == VIEW_LIST else VIEW_GRID


def set_recent_view_mode(mode: str, *, settings=None) -> None:
    qs = settings if settings is not None else _settings()
    qs.setValue(_VIEW_KEY, VIEW_LIST if mode == VIEW_LIST else VIEW_GRID)
    qs.sync()


def get_recent_sort_mode(*, settings=None) -> str:
    qs = settings if settings is not None else _settings()
    value = str(qs.value(_SORT_KEY, SORT_MODIFIED) or SORT_MODIFIED).strip().lower()
    return normalize_recent_sort_mode(value)


def set_recent_sort_mode(mode: str, *, settings=None) -> None:
    qs = settings if settings is not None else _settings()
    qs.setValue(_SORT_KEY, normalize_recent_sort_mode(mode))
    qs.sync()


def get_recent_sort_order(*, settings=None) -> str:
    qs = settings if settings is not None else _settings()
    value = str(qs.value(_SORT_ORDER_KEY, SORT_DESC) or SORT_DESC).strip().lower()
    return SORT_ASC if value == SORT_ASC else SORT_DESC


def set_recent_sort_order(order: str, *, settings=None) -> None:
    qs = settings if settings is not None else _settings()
    qs.setValue(
        _SORT_ORDER_KEY,
        SORT_ASC if str(order).strip().lower() == SORT_ASC else SORT_DESC,
    )
    qs.sync()


def _parse_records(raw: Any) -> list[RecentProjectRecord]:
    if not raw:
        return []
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        logger.debug("Failed to parse recent_projects settings", exc_info=True)
        return []
    if not isinstance(data, list):
        return []
    out: list[RecentProjectRecord] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        record = RecentProjectRecord.from_dict(item)
        if record is None:
            continue
        key = _normalize_path(record.path)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def _write_records(settings, records: Sequence[RecentProjectRecord]) -> None:
    payload = json.dumps([r.to_dict() for r in records], ensure_ascii=False)
    settings.setValue(_SETTINGS_KEY, payload)
    settings.sync()
