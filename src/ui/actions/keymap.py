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


def _binding_priority(action_id: str, *, owner_tab: str | None) -> tuple:
    """Lower sorts first and wins chord conflicts (platform before tab)."""
    if action_id == "platform.settings":
        return (0, "")
    if owner_tab is None:
        return (1, action_id)
    return (2, f"{owner_tab}:{action_id}")


def exclusive_overrides(
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: Mapping[str, str] | None,
    *,
    prefer_action_id: str | None = None,
) -> dict[str, str]:
    """Return overrides where each chord is owned by at most one action.

    ``defaults`` maps ``action_id → (default_shortcut, owner_tab)``.
    Conflicting actions other than the winner get an explicit unbound override
    (``""``) so their defaults cannot reclaim the chord.
    """
    result = {
        key: normalize_sequence(value) if value else ""
        for key, value in (overrides or {}).items()
    }
    # action_id → effective chord
    effective: dict[str, str] = {}
    for action_id, (default, _owner) in defaults.items():
        chord = effective_shortcut_for_id(
            action_id, default=default, overrides=result
        )
        if chord:
            effective[action_id] = chord

    by_chord: dict[str, list[str]] = {}
    for action_id, chord in effective.items():
        by_chord.setdefault(chord, []).append(action_id)

    for chord, action_ids in by_chord.items():
        if len(action_ids) < 2:
            continue
        ranked = sorted(
            action_ids,
            key=lambda aid: (
                0 if prefer_action_id and aid == prefer_action_id else 1,
                _binding_priority(aid, owner_tab=defaults[aid][1]),
            ),
        )
        for action_id in ranked[1:]:
            # Explicitly unbind losers so defaults cannot keep the chord.
            result[action_id] = ""
    return result


def steal_chord_in_overrides(
    *,
    action_id: str,
    chord: str | None,
    defaults: Mapping[str, tuple[str | None, str | None]],
    overrides: dict[str, str],
) -> dict[str, str]:
    """Assign ``chord`` to ``action_id`` and unbind every other owner of it."""
    normalized = normalize_sequence(chord)
    default = defaults.get(action_id, (None, None))[0]
    default_norm = normalize_sequence(default)
    next_overrides = dict(overrides)
    if not normalized:
        next_overrides[action_id] = ""
    elif normalized == default_norm:
        next_overrides.pop(action_id, None)
    else:
        next_overrides[action_id] = normalized
    return exclusive_overrides(
        defaults, next_overrides, prefer_action_id=action_id
    )


@dataclass(frozen=True, slots=True)
class KeymapDefaultEntry:
    """Metadata-only catalog row for Settings (no run / target)."""

    action_id: str
    label_key: str
    default_shortcut: str | None = None
    owner_tab: str | None = None
    breadcrumb: tuple[str, ...] = ()
    description_key: str | None = None
    # Same semantics as ActionDescriptor — mode names / aliases for the
    # Settings → Keyboard filter (e.g. SSIM → Difference Mode cycle).
    search_keys: tuple[str, ...] = ()
    search_terms: tuple[str, ...] = ()


def keymap_entry_rank(
    entry: KeymapDefaultEntry,
    query: str,
    *,
    extra_search_terms: tuple[str, ...] = (),
) -> int | None:
    """Find Action–style rank for a keyboard binder row, or ``None`` if no match.

    Searches the same fields as the command palette (id, label, description,
    breadcrumb, chord, ``search_keys`` / ``search_terms``) plus any extras
    (group title, effective chord). Uncached so extras never pollute the
    palette haystack cache.
    """
    from ui.actions.registry import (
        _normalize,
        action_query_rank,
        compute_action_haystacks,
    )

    needle = _normalize((query or "").strip())
    if not needle:
        return 0
    haystacks = compute_action_haystacks(
        action_id=entry.action_id,
        label_key=entry.label_key,
        description_key=entry.description_key,
        breadcrumb=entry.breadcrumb,
        shortcut=entry.default_shortcut,
        search_keys=entry.search_keys,
        search_terms=entry.search_terms + tuple(
            term for term in extra_search_terms if term
        ),
    )
    return action_query_rank(needle, haystacks=haystacks)


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
