"""Resolve effective action shortcuts (defaults + user overrides)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from core.actions.types import ActionDescriptor

try:
    from PySide6.QtGui import QKeySequence
except Exception:  # pragma: no cover - import-time without Qt in tiny unit tests
    QKeySequence = None  # type: ignore[misc, assignment]


def normalize_sequence(sequence: str | None) -> str:
    """Return PortableText form, or empty string if unbound / invalid."""
    text = (sequence or "").strip()
    if not text:
        return ""
    if QKeySequence is None:
        return text
    key = QKeySequence(text)
    if key.isEmpty():
        return ""
    return key.toString(QKeySequence.SequenceFormat.PortableText)


def effective_shortcut(
    action: ActionDescriptor,
    overrides: Mapping[str, str] | None,
) -> str | None:
    """Resolve display/runtime chord.

    - key missing in overrides → descriptor default
    - key present with empty string → unbound
    - key present with value → that sequence (normalized)
    """
    overrides = overrides or {}
    if action.action_id in overrides:
        normalized = normalize_sequence(overrides[action.action_id])
        return normalized or None
    default = normalize_sequence(action.shortcut)
    return default or None


def effective_shortcut_for_id(
    action_id: str,
    *,
    default: str | None,
    overrides: Mapping[str, str] | None,
) -> str | None:
    overrides = overrides or {}
    if action_id in overrides:
        normalized = normalize_sequence(overrides[action_id])
        return normalized or None
    normalized = normalize_sequence(default)
    return normalized or None


def chord_conflicts(
    bindings: Mapping[str, str | None],
) -> dict[str, list[str]]:
    """Map normalized chord → action_ids that share it (len > 1 only)."""
    by_chord: dict[str, list[str]] = {}
    for action_id, sequence in bindings.items():
        chord = normalize_sequence(sequence)
        if not chord:
            continue
        by_chord.setdefault(chord, []).append(action_id)
    return {chord: ids for chord, ids in by_chord.items() if len(ids) > 1}


@dataclass(frozen=True, slots=True)
class KeymapDefaultEntry:
    """Metadata-only catalog row for Settings (no run / target)."""

    action_id: str
    label_key: str
    default_shortcut: str | None = None
    owner_tab: str | None = None
    breadcrumb: tuple[str, ...] = ()


class KeymapDefaultsRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, KeymapDefaultEntry] = {}

    def register(self, entry: KeymapDefaultEntry) -> None:
        if not entry.action_id:
            raise ValueError("KeymapDefaultEntry.action_id must be non-empty")
        self._by_id[entry.action_id] = entry

    def all_entries(self) -> list[KeymapDefaultEntry]:
        return sorted(
            self._by_id.values(),
            key=lambda e: (e.owner_tab or "", e.action_id),
        )

    def clear(self) -> None:
        self._by_id.clear()


def collect_bindings(
    actions: Iterable[ActionDescriptor],
    overrides: Mapping[str, str] | None,
) -> dict[str, str | None]:
    return {
        action.action_id: effective_shortcut(action, overrides) for action in actions
    }
